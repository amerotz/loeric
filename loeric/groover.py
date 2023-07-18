import mido
import jsonmerge
import copy
import random
import json
import numpy as np

import tune as tu
import contour as cnt

CUT = "cut"
DROP = "drop"
ROLL = "roll"
SLIDE = "slide"


class UnknownContourError(Exception):
    """Raised if trying to set a contour whose name does not correspond to any of the Groover's contours."""

    pass


class Groover:
    """The class responsible for playback, ornamentation and human interaction."""

    def __init__(
        self,
        tune: tu.Tune,
        bpm: int = None,
        midi_channel: int = 0,
        transpose: int = 0,
        random_weight: float = 0,
        human_impact: float = 0,
        apply_savgol: bool = True,
        config_file: str = None,
    ):
        """
        Initialize the groover class by setting user-defined parameters and creating the contours.
        Any parameters set on class instatiation that are also present in the configuration file will be overwritten. To preserve command line arguments, omit the corresponding fields from the  configuration file.

        :param tune: the tune that will be performed.
        :param bpm: the user-defined tempo in bpm for the tune.
        :param midi_channel: the midi output channel for all messages.
        :param transpose: the number of semitones by which to transpose the tune.
        :param random_weight: the weight of the random component in contour generation.
        :param apply_savgol: whether or not to apply savgol filtering in contour generation. True by default (recommended).
        :param config_file: the path to the configuration file (must be a JSON file).
        """

        # tune
        self._tune = tune

        # offset for messages after ornaments
        self._offset = 0

        self._config = {
            "velocity": {
                "weights": [0.2, 0.3, 0.1, 0.2, 0.2],
                "random": random_weight,
                "savgol": apply_savgol,
                "shift": False,
                "human_impact": human_impact,
            },
            "tempo": {
                "weights": [0.25, 0.1, 0.3, 0.25, 0.1],
                "random": random_weight,
                "savgol": apply_savgol,
                "shift": True,
                "human_impact": human_impact,
            },
            "ornament": {
                "weights": [0.2, 0.35, 0.15, 0.15, 0.2],
                "random": random_weight,
                "savgol": apply_savgol,
                "shift": False,
                "human_impact": human_impact,
            },
            "probabilities": {
                "drop": 0.1,
                "roll": 0.5,
                "slide": 0.5,
                "cut": 0.5,
                "error": 0.5,
            },
            "values": {
                "bend_resolution": 32,
                "cut_beat_divisions": 24,
                "roll_beat_divisions": 12,
                "slide_beat_divisions": 3,
                "slide_pitch_threshold": 5,
                "tempo_warp_bpms": 0,
                "beat_velocity_increase": 16,
                "midi_channel": midi_channel,
                "bpm": bpm,
                "transpose": transpose,
                "min_velocity": 0,
                "max_velocity": 127,
            },
        }

        if config_file is not None:
            with open(config_file, "r") as f:
                config_file = json.load(f)
            self._config = jsonmerge.merge(self._config, config_file)

        # generate all parameter settings and contours
        self._instantiate()

    def _instantiate(self):
        """
        Generate all parameter settings following the current configuration.
        """

        # set parameters
        if self._config["values"]["bpm"] is None:
            self._user_tempo = self._tune.tempo
        else:
            self._user_tempo = mido.bpm2tempo(self._config["values"]["bpm"])

        self._midi_channel = self._config["values"]["midi_channel"]
        self._transpose_semitones = self._config["values"]["transpose"]

        # create contours
        self._contours = {}

        # velocity contour
        self._contours["velocity"] = cnt.IntensityContour()
        self._contours["velocity"].calculate(
            self._tune,
            weights=np.array(self._config["velocity"]["weights"]),
            random_weight=self._config["velocity"]["random"],
            savgol=self._config["velocity"]["savgol"],
            shift=self._config["velocity"]["shift"],
        )
        # tempo contour
        self._contours["tempo"] = cnt.IntensityContour()
        self._contours["tempo"].calculate(
            self._tune,
            weights=np.array(self._config["tempo"]["weights"]),
            random_weight=self._config["tempo"]["random"],
            savgol=self._config["tempo"]["savgol"],
            shift=self._config["tempo"]["shift"],
        )
        # ornament contour
        self._contours["ornament"] = cnt.IntensityContour()
        self._contours["ornament"].calculate(
            self._tune,
            weights=np.array(self._config["ornament"]["weights"]),
            random_weight=self._config["ornament"]["random"],
            savgol=self._config["ornament"]["savgol"],
            shift=self._config["ornament"]["shift"],
        )

        # error contour
        self._contours["error"] = cnt.RandomContour()
        self._contours["error"].calculate(self._tune, extremes=(0, 1))

        # message length contour
        self._contours["message length"] = cnt.MessageLengthContour()
        self._contours["message length"].calculate(self._tune)
        # pich difference
        self._contours["pitch difference"] = cnt.PitchDifferenceContour()
        self._contours["pitch difference"].calculate(self._tune)

        # object holding each contour's value in a given moment
        self._contour_values = {}
        # init the human contour
        self._contour_values["human"] = 0.5
        # init all contours
        for contour_name in self._contours:
            self._contour_values[contour_name] = 0.5

    def advance_contours(self) -> None:
        """
        Retrieve the next value of each contour and store it for future use.
        """

        # update all contours
        for contour_name in self._contours:
            self._contour_values[contour_name] = self._contours[contour_name].next()

        # add the human part
        if self._contour_values["human"] is not None:
            for contour_name in ["velocity", "tempo", "ornament"]:
                hi = self._config[contour_name]["human_impact"]
                self._contour_values[contour_name] *= 1 - hi
                self._contour_values[contour_name] += hi * self._contour_values["human"]

    def set_contour_value(self, contour_name: str, value: float) -> None:
        """
        Set the value of a given contour to a given value until the update.

        :param contour_name: the name of the contour.
        :param value: the value to set the contour to.

        :raise groover.UnknownContourError: if the contour name does not correspond to any of the Groover's contours.
        """
        if contour_name not in self._contour_values:
            raise UnknownContourError
        self._contour_values[contour_name] = value

    def perform(self, message: mido.Message) -> list[mido.Message]:
        """
        'Perform' a single note event by affecting its timing, pitch, velocity and adding ornaments.

        :param message: the midi message to perform.

        :return: the list of midi messages corresponding to the input message's performance.
        """

        # work on a deepcopy to avoid side effects
        new_message = copy.deepcopy(message)
        new_message.time -= self._offset
        self._offset = 0

        # change midi channel
        new_message.channel = self._midi_channel

        # if it's a note message
        if tu.is_note(new_message):
            # transpose note
            new_message.note += self._transpose_semitones

        # check if note on event
        is_note_on = tu.is_note_on(new_message)
        if is_note_on:
            # advance the contours
            self.advance_contours()

        # change note duration
        new_message.time = self._duration_of(new_message.time)

        # change loudness
        if is_note_on:
            new_message.velocity = self._current_velocity

        notes = [new_message]

        # modify the note
        if is_note_on:
            # create ornaments
            if self.can_generate_ornament():
                # choose which ornament
                ornament_type = self.choose_ornament(new_message)

                # generate it
                if ornament_type is not None:
                    notes = self.generate_ornament(new_message, ornament_type)

        return notes

    @property
    def _slide_duration(self):
        """
        :return: the duration of a slide.
        """
        return self._duration_of(
            self._tune.beat_duration / self._config["values"]["slide_beat_divisions"]
        )

    @property
    def _cut_duration(self):
        """
        :return: the duration of a cut note.
        """
        return self._duration_of(
            self._tune.beat_duration / self._config["values"]["cut_beat_divisions"]
        )

    @property
    def _roll_duration(self):
        """
        :return: the duration of a single note in a roll.
        """

        return self._duration_of(
            self._tune.beat_duration / self._config["values"]["roll_beat_divisions"]
        )

    @property
    def tempo(self):
        """
        :return: the user-set tempo.
        """
        return self._user_tempo

    def generate_ornament(
        self, message: mido.Message, ornament_type: str
    ) -> list[mido.Message]:
        """
        Generate the sequence of notes corresponding to the chosen ornament.

        :param message: the midi message to ornament.
        :param ornament_type: the type of ornament to generate.

        :return: the list of midi events corresponding to the chosen ornament.
        """

        ornaments = []
        message_length = self._duration_of(self._contour_values["message length"])
        if ornament_type == CUT:
            # generate a cut
            cut = copy.deepcopy(message)
            cut_index = self._tune.semitones_from_tonic(message.note)
            cut.note = tu.above_approach_scale[cut_index] + message.note
            cut.velocity = self._current_velocity
            duration = min(
                self._cut_duration,
                message_length / 3,
            )
            cut.time = 0

            # note on
            ornaments.append(cut)
            # note off
            ornaments.append(
                mido.Message(
                    "note_off",
                    channel=cut.channel,
                    note=cut.note,
                    time=duration,
                    velocity=0,
                )
            )

            ornaments.append(message)
            # update offset for next message to make it shorter
            self._offset = duration

        elif ornament_type == ROLL:
            ornament_index = self._tune.semitones_from_tonic(message.note)
            message_length = min(
                self._roll_duration,
                message_length / 4,
            )

            # calculate cut
            upper_pitch = tu.above_approach_scale[ornament_index] + message.note
            upper = mido.Message(
                "note_on",
                note=upper_pitch,
                channel=message.channel,
                time=0,
                velocity=self._current_velocity,
            )
            upper_off = mido.Message(
                "note_off",
                note=upper_pitch,
                channel=message.channel,
                time=message_length,
                velocity=0,
            )

            # change original note
            original_1 = copy.deepcopy(message)
            original_1.time = 0
            original_1.velocity = self._current_velocity
            or_1_off = mido.Message(
                "note_off",
                note=message.note,
                channel=message.channel,
                time=message_length,
                velocity=0,
            )

            # calculate cut
            lower_pitch = tu.below_approach_scale[ornament_index] + message.note
            lower = mido.Message(
                "note_on",
                note=lower_pitch,
                channel=message.channel,
                time=0,
                velocity=self._current_velocity,
            )
            lower_off = mido.Message(
                "note_off",
                note=lower_pitch,
                channel=message.channel,
                time=message_length,
                velocity=0,
            )

            # append note on and off events
            ornaments.append(upper)
            ornaments.append(upper_off)

            ornaments.append(original_1)
            ornaments.append(or_1_off)

            ornaments.append(lower)
            ornaments.append(lower_off)

            ornaments.append(message)

            self._offset = 3 * message_length

        elif ornament_type == SLIDE:
            # append original note
            original = copy.deepcopy(message)
            original.time = 0
            original.velocity = self._current_velocity
            ornaments.append(original)

            # calculate pitch bend
            note_index = self._tune.semitones_from_tonic(message.note)
            diff = tu.below_approach_scale[note_index]
            bend = max(min(4096.0 * diff, 8191), -8192)

            # calculate duration
            resolution = self._config["values"]["bend_resolution"]
            slide_time = message_length / 4
            self._offset = slide_time
            duration = slide_time / resolution

            # append messages
            for i in range(resolution, -1, -1):
                p = i / resolution
                p **= 5
                p *= bend
                p = int(p)
                ornaments.append(
                    mido.Message(
                        "pitchwheel", channel=message.channel, pitch=p, time=duration
                    )
                )
            ornaments.append(
                mido.Message("pitchwheel", channel=message.channel, pitch=0, time=0)
            )
        elif ornament_type == DROP:
            pass

        return ornaments

    def choose_ornament(self, message: mido.Message) -> str:
        """
        Evaluate the ornament specific rules and chooose how the note will be ornamented.

        :param message: the midi message to ornament.

        :return: the chosen ornament type.
        """
        options = []

        is_beat = self._tune.is_on_a_beat()
        message_length = self._duration_of(self._contour_values["message length"])

        if is_beat and random.uniform(0, 1) < self._config["probabilities"]["cut"]:
            options.append(CUT)

        if (
            random.uniform(0, 1) < self._config["probabilities"]["roll"]
            and message_length >= self._roll_duration * 4
        ):
            options.append(ROLL)

        if (
            (is_beat and message_length > self._slide_duration)
            or self._contour_values["pitch difference"]
            >= self._config["values"]["slide_pitch_threshold"]
        ) and random.uniform(0, 1) < self._config["probabilities"]["slide"]:
            options.append(SLIDE)

        if not is_beat and random.uniform(0, 1) < self._config["probabilities"]["drop"]:
            options.append(DROP)

        if len(options) == 0:
            return None
        return random.choice(options)

    def can_generate_ornament(self) -> bool:
        """
        :return: whether or not to generate an ornament given the current ornament contour.
        """
        prob = self._contour_values["ornament"]
        return random.choices([True, False], weights=[prob, 1 - prob], k=1)[0]

    def _duration_of(self, time: float) -> float:
        """
        Calculate the duration in seconds in the current tempo of the input duration, given in tune tempo.

        :param time: the input time value in seconds, given the original tempo.

        :return: the new duration of the input time value in seconds.
        """
        tempo_ratio = self._current_tempo / self._tune.tempo
        return tempo_ratio * time

    def reset(self) -> None:
        """
        Reset all contours so that the next call to `next()` will yield the first value of each contour.
        """
        for contour_name in self._contours:
            self._contours[contour_name].reset()

    @property
    def _current_tempo(self) -> int:
        """
        :return: the current tempo given the value of the tempo contour.
        """
        # version 1
        # warp as a percentage of current tempo
        """
        TEMPO_WARP = 0.1
        value = int(
            2 * TEMPO_WARP * self._user_tempo * (self._contour_values["tempo"] - 0.5)
        )
        """
        # version 2
        # warp as a fixed maximum amount of bpm
        bpm = mido.tempo2bpm(self._user_tempo)
        value = (
            2
            * self._config["values"]["tempo_warp_bpms"]
            * (self._contour_values["tempo"] - 0.5)
        )

        return mido.bpm2tempo(int(bpm + value))

    @property
    def _current_velocity(self) -> int:
        """
        :return: the current velocity given the value of the velocity contour.
        """
        max_velocity = self._config["values"]["max_velocity"]
        min_velocity = self._config["values"]["min_velocity"]
        velocity_range = max_velocity - min_velocity
        value = int(self._contour_values["velocity"] * velocity_range)
        if self._tune.is_on_a_beat():
            value += self._config["values"]["beat_velocity_increase"]

        # clamp velocity
        value = max(min(value, max_velocity), min_velocity)
        return value
