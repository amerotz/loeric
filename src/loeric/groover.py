import mido
import jsonmerge
import copy
import random
import json
import numpy as np
import music21 as m21

from collections import defaultdict

from . import tune as tu
from . import contour as cnt
from . import loeric_utils as lu


CUT = "cut"
DROP = "drop"
ROLL = "roll"
SLIDE = "slide"
ERROR = "error"


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
        diatonic_errors: bool = True,
        random_weight: float = 0,
        human_impact: float = 0,
        high_loud_weight: float = 0.25,
        seed: int = 42,
        apply_savgol: bool = True,
        config_file: str = None,
    ):
        """
        Initialize the groover class by setting user-defined parameters and creating the contours.
        Any parameters set on class instatiation that are also present in the configuration file will be overwritten. To preserve command line arguments, omit the corresponding fields from the  configuration file.

        :param tune: the tune that will be performed.
        :param bpm: the user-defined tempo in bpm for the tune.
        :param midi_channel: the midi output channel for all note messages. Drone messages will be sent on midi_channel + 1 if not specified otherwise in the configuration.
        :param transpose: the number of semitones by which to transpose the tune.
        :param diatonic_errors: whether or not error generation should be quantized to the tune's mode.
        :param random_weight: the weight of the random component in contour generation.
        :param human_impact: the weight of the external control signal.
        :param seed: the random seed of the performance.
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
                "high_loud_weight": high_loud_weight,
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
                "roll": 1,
                "slide": 1,
                "cut": 1,
                "error": 0.1,
            },
            "values": {
                "bend_resolution": 32,
                "cut_eight_fraction": 0.2,
                "cut_velocity_fraction": 0.8,
                "roll_eight_fraction": 0.8,
                "slide_eight_fraction": 0.66,
                "slide_pitch_threshold": 6,
                "tempo_warp_bpms": 10,
                "beat_velocity_increase": 16,
                "midi_channel": midi_channel,
                "bpm": bpm,
                "transpose": transpose,
                "min_velocity": 0,
                "max_velocity": 127,
                "max_pitch_error": 2,
                "min_pitch_error": -2,
                "diatonic_errors": diatonic_errors,
                "use_old_tempo_warp": False,
                "old_tempo_warp": 0.1,
                "seed": seed,
            },
            "automation": {
                "velocity": 46,
                "tempo": 47,
                "ornament": 48,
                "human": 49,
            },
            "harmony": {
                "chord_score": [1, 0, 0, 0, 0, 1, 0, 0, 0.25, 0.25, 0, 0],
                "allowed_chords": [2, 0, 1, 0, 1, 2, 0, 2, 0, 1, 0, 0],
                "chords_per_bar": 2,
            },
            "drone": {
                "active": False,
                "midi_channel": midi_channel + 1,
                "allowed_notes": [55, 62, 69, 76],
            },
            "approach_from_above": {},
            "approach_from_below": {},
        }

        if config_file is not None:
            with open(config_file, "r") as f:
                config_file = json.load(f)
            self._config = jsonmerge.merge(self._config, config_file)
            config_hash = int(hash(str(config_file))) % 2**31
            self._config["values"]["seed"] = config_hash + seed

        # generate all parameter settings and contours
        self._instantiate()

    def _instantiate(self):
        """
        Generate all parameter settings following the current configuration.
        """

        # random seed
        random.seed(self._config["values"]["seed"])
        np.random.seed(self._config["values"]["seed"])

        # set parameters
        if self._config["values"]["bpm"] is None:
            self._user_tempo = self._tune.tempo
        else:
            self._user_tempo = mido.bpm2tempo(self._config["values"]["bpm"])

        self._midi_channel = self._config["values"]["midi_channel"]
        self._transpose_semitones = self._config["values"]["transpose"]
        # table for pitch errors
        self._pitch_errors = defaultdict(int)

        # create contours
        self._contours = {}

        # velocity contour
        velocity_intensity_contour = cnt.IntensityContour()
        velocity_intensity_contour.calculate(
            self._tune,
            weights=np.array(self._config["velocity"]["weights"]),
            random_weight=self._config["velocity"]["random"],
            savgol=self._config["velocity"]["savgol"],
            shift=self._config["velocity"]["shift"],
        )

        velocity_pitch_contour = cnt.PitchContour()
        velocity_pitch_contour.calculate(self._tune)

        self._contours["velocity"] = cnt.weighted_sum(
            [velocity_intensity_contour, velocity_pitch_contour],
            np.array(
                [
                    1 - self._config["velocity"]["high_loud_weight"],
                    self._config["velocity"]["high_loud_weight"],
                ]
            ),
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

        # message length contour
        self._contours["message length"] = cnt.MessageLengthContour()
        self._contours["message length"].calculate(self._tune)
        # pich difference
        self._contours["pitch difference"] = cnt.PitchDifferenceContour()
        self._contours["pitch difference"].calculate(self._tune)

        self._contours["harmony"] = cnt.HarmonicContour()
        self._contours["harmony"].calculate(
            self._tune,
            np.array(
                self._config["harmony"]["chord_score"],
            ),
            chords_per_bar=self._config["harmony"]["chords_per_bar"],
            allowed_chords=np.array(self._config["harmony"]["allowed_chords"]),
            transpose=self._transpose_semitones,
        )

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
        # change note duration
        new_message.time = self._duration_of(new_message.time)
        new_message.time -= self._offset

        self._offset = 0

        # change midi channel
        new_message.channel = self._midi_channel

        # if it's a note message
        if lu.is_note(new_message):
            # transpose note
            new_message.note += self._transpose_semitones

        # change note offs of errors
        if lu.is_note_off(new_message):
            key = new_message.note
            if key in self._pitch_errors:
                value = self._pitch_errors[key]
                new_message.note += value

                # reset error
                del self._pitch_errors[key]

        # check if note on event
        is_note_on = lu.is_note_on(new_message)
        if is_note_on:
            # advance the contours
            self.advance_contours()

        # change loudness
        if is_note_on:
            new_message.velocity = self._current_velocity

        notes = []

        # add contour information as MIDI CC
        for contour_name in self._config["automation"]:
            notes.append(
                mido.Message(
                    "control_change",
                    channel=self._config["values"]["midi_channel"],
                    control=self._config["automation"][contour_name],
                    value=round(self._contour_values[contour_name] * 127),
                    time=0,
                )
            )

        # add explicit tempo information
        notes.append(mido.MetaMessage("set_tempo", tempo=self._current_tempo, time=0))

        # add actual message
        notes.append(new_message)

        # modify the note
        if is_note_on:
            # create ornaments
            if self.can_generate_ornament():
                # choose which ornament
                ornament_type = self.choose_ornament(new_message)

                # generate it
                if ornament_type is not None:
                    notes = self.generate_ornament(new_message, ornament_type)

        # make sure time is not negative
        for note in notes:
            note.time = max(0, note.time)

        # add drone
        if self._config["drone"]["active"]:
            # figure out what note is allowed depending on harmony
            harmony = int(self._contour_values["harmony"] % 12)
            drone_notes = np.array(self._config["drone"]["allowed_notes"])

            # filter roots and fifths of chord
            index = np.argwhere(
                np.bitwise_and(
                    np.bitwise_and(
                        np.bitwise_and(
                            np.in1d(
                                (12 + drone_notes - harmony) % 12,
                                lu.get_chord_pitches(
                                    int(self._contour_values["harmony"])
                                ),
                            ),
                            drone_notes - new_message.note <= 0,
                        ),
                        new_message.note - drone_notes > 6,
                    ),
                    new_message.note - drone_notes <= 12,
                )
            )
            if len(index) != 0:
                drone_notes = drone_notes[index]
                index = np.argmin(abs(drone_notes - new_message.note))
                drone = int(drone_notes[index])

                new_notes = []
                i = 0
                while i < len(notes):
                    new_notes.append(notes[i])
                    if lu.is_note(notes[i]):
                        new_notes.append(
                            mido.Message(
                                type=notes[i].type,
                                channel=self._config["drone"]["midi_channel"],
                                note=drone,
                                velocity=self._current_velocity,
                                time=0,
                            )
                        )
                    i += 1
                notes = new_notes

        return notes

    def get_end_notes(self) -> list[mido.Message]:
        """
        Generate an end note for the tune based on its key.
        :return: the midi messages containing the end note
        """
        # get root and range
        root = int(self._contour_values["harmony"] % 12)
        low, high = self._tune.ambitus

        # select suitable pitches (e.g. any root, third, fifth within range)
        pitches = np.arange(
            start=low + self._transpose_semitones,
            stop=high + 1 + self._transpose_semitones,
            step=1,
        )

        # major or minor
        chord_pitches = lu.get_chord_pitches(self._contour_values["harmony"])

        pitches = pitches[np.in1d((12 + pitches - root) % 12, chord_pitches)]

        # sample
        end_pitch = random.choice(pitches)

        # get duration (quarter note)
        duration = self._eight_duration * 4

        # create msgs
        on_msg = mido.Message(
            "note_on",
            channel=self._midi_channel,
            note=end_pitch,
            time=0,
            velocity=self._current_velocity,
        )
        off_msg = mido.Message(
            "note_off",
            channel=self._midi_channel,
            note=end_pitch,
            time=duration,
            velocity=0,
        )

        return [on_msg, off_msg]

    @property
    def _slide_duration(self) -> float:
        """
        :return: the duration of a slide.
        """
        return self._eight_duration * self._config["values"]["slide_eight_fraction"]

    @property
    def _cut_duration(self) -> float:
        """
        :return: the duration of a cut note.
        """
        return self._eight_duration * self._config["values"]["cut_eight_fraction"]

    @property
    def _roll_duration(self) -> float:
        """
        :return: the duration of a single note in a roll.
        """

        return self._eight_duration * self._config["values"]["roll_eight_fraction"]

    @property
    def _eight_duration(self) -> float:
        """
        :return: the duration of a eight note in seconds at current tempo.
        """
        return 30 / mido.tempo2bpm(self._current_tempo)

    @property
    def tempo(self) -> int:
        """
        :return: the user-set tempo.
        """
        return self._user_tempo

    def approach_from_above(self, note_number: int, tune: tu.Tune) -> int:
        """
        Return the midi note number to approach the given note from above.
        If no special approach rule is specified in the configuration file, it will return the next note in the scale of the tune's key from the given note.

        :param note_number: the note to approach.
        :param tune: the reference tune.

        :return: the note used the approach the given note from above.
        """
        note_name = m21.pitch.Pitch(midi=note_number).nameWithOctave
        # use configuration
        if note_name in self._config["approach_from_above"]:
            pitch = m21.pitch.Pitch(self._config["approach_from_above"][note_name])
            return pitch.midi
        # use normal scale
        else:
            index = self._tune.semitones_from_tonic(note_number)
            return lu.above_approach_scale[index] + note_number

    def approach_from_below(self, note_number: int, tune: tu.Tune) -> int:
        """
        Return the midi note number to approach the given note from below.
        If no special approach rule is specified in the configuration file, it will return the previous note in the scale of the tune's key from the given note.

        :param note_number: the note to approach.
        :param tune: the reference tune.

        :return: the note used the approach the given note from below.
        """
        note_name = m21.pitch.Pitch(midi=note_number).nameWithOctave
        # use configuration
        if note_name in self._config["approach_from_below"]:
            pitch = m21.pitch.Pitch(self._config["approach_from_below"][note_name])
            return pitch.midi
        # use normal scale
        else:
            index = self._tune.semitones_from_tonic(note_number)
            return lu.below_approach_scale[index] + note_number

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
            cut.note = self.approach_from_above(message.note, self._tune)
            cut.velocity = int(
                self._current_velocity * self._config["values"]["cut_velocity_fraction"]
            )
            duration = self._cut_duration
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
            self._offset += duration

        elif ornament_type == ROLL:
            original_length = self._roll_duration
            cut_length = self._eight_duration - self._roll_duration
            cut_velocity = int(
                self._current_velocity * self._config["values"]["cut_velocity_fraction"]
            )

            # first note
            original_0 = copy.deepcopy(message)
            original_0.time = 0
            original_0.velocity = self._current_velocity
            or_0_off = mido.Message(
                "note_off",
                note=message.note,
                channel=message.channel,
                time=original_length,
                velocity=0,
            )

            # calculate cut
            upper_pitch = self.approach_from_above(message.note, self._tune)
            upper = mido.Message(
                "note_on",
                note=upper_pitch,
                channel=message.channel,
                time=0,
                velocity=cut_velocity,
            )
            upper_off = mido.Message(
                "note_off",
                note=upper_pitch,
                channel=message.channel,
                time=cut_length,
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
                time=original_length,
                velocity=0,
            )

            # calculate cut
            lower_pitch = self.approach_from_below(message.note, self._tune)
            lower = mido.Message(
                "note_on",
                note=lower_pitch,
                channel=message.channel,
                time=0,
                velocity=cut_velocity,
            )
            lower_off = mido.Message(
                "note_off",
                note=lower_pitch,
                channel=message.channel,
                time=cut_length,
                velocity=0,
            )

            # append note on and off events
            ornaments.append(original_0)
            ornaments.append(or_0_off)

            ornaments.append(upper)
            ornaments.append(upper_off)

            ornaments.append(original_1)
            ornaments.append(or_1_off)

            ornaments.append(lower)
            ornaments.append(lower_off)

            message.time = 0
            ornaments.append(message)

            self._offset += 2 * self._eight_duration

        elif ornament_type == SLIDE:
            # append original note
            original = copy.deepcopy(message)
            original.time = 0
            original.velocity = self._current_velocity
            ornaments.append(original)

            # calculate pitch bend
            diff = self.approach_from_below(message.note, self._tune) - message.note
            bend = max(min(4096.0 * diff, 8191), -8192)

            # calculate duration
            resolution = self._config["values"]["bend_resolution"]
            slide_time = message_length / 4
            self._offset += slide_time
            duration = slide_time / resolution

            # append messages
            for i in range(resolution, -1, -1):
                p = i / resolution
                p **= random.uniform(0.25, 0.5)
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
        elif ornament_type == ERROR:
            max_limit = self._config["values"]["max_pitch_error"]
            min_limit = self._config["values"]["min_pitch_error"]
            # generate error
            value = random.randint(min_limit, max_limit)

            # correct if diatonic errors are required
            if self._config["values"]["diatonic_errors"]:
                new_note = message.note + value

                # get note position in scale
                note_index = self._tune.semitones_from_tonic(new_note)

                # if quantization needed
                if lu.needs_pitch_quantization[note_index]:
                    # check both quantizing up and down
                    opt = {
                        abs(value - 1): -1,
                        abs(value + 1): 1,
                    }
                    # if one option leaves the note unchanged, use the other
                    if min(opt) == 0:
                        value += opt[max(opt)]
                    else:
                        value -= opt[min(opt)]

            # record error for that note for later note off event
            self._pitch_errors[message.note] = value
            # create the new message
            new_message = copy.deepcopy(message)
            new_message.note += value
            ornaments.append(new_message)

            perc = random.uniform(0.4, 0.9)
            off_message = mido.Message(
                "note_off",
                note=new_message.note,
                velocity=0,
                time=message_length * perc,
            )
            ornaments.append(off_message)
            self._offset += message_length * perc

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

        if (
            message_length >= 0.75 * self._eight_duration
            and (is_beat or self._contour_values["pitch difference"] == 0)
            and random.uniform(0, 1) < self._config["probabilities"]["cut"]
        ):
            options.append(CUT)

        if (
            random.uniform(0, 1) < self._config["probabilities"]["roll"]
            # value of a dotted quarter
            and message_length - 3 * self._eight_duration > -0.01
        ):
            # return ROLL
            options.append(ROLL)

        if (
            (is_beat and message_length > self._slide_duration)
            or self._contour_values["pitch difference"]
            >= self._config["values"]["slide_pitch_threshold"]
        ) and random.uniform(0, 1) < self._config["probabilities"]["slide"]:
            options.append(SLIDE)

        if not is_beat and random.uniform(0, 1) < self._config["probabilities"]["drop"]:
            options.append(DROP)

        if random.uniform(0, 1) < self._config["probabilities"]["error"]:
            options.append(ERROR)

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
        :return: the current tempo given the value of the tempo contour. If the option `use_old_tempo_warp` is set to `True` the contour affects tempo in terms of percentage of the original one (e.g. 20% faster); otherwise in terms of a fixed amount of bpms (e.g. 10 bpms faster).
        """
        # (old) version 1
        # warp as a percentage of current tempo
        if self._config["values"]["use_old_tempo_warp"]:
            tempo_warp = self._config["values"]["old_tempo_warp"]
            value = int(
                2
                * tempo_warp
                * self._user_tempo
                * (self._contour_values["tempo"] - 0.5)
            )
            return int(self._user_tempo + value)

        # version 2
        # warp as a fixed maximum amount of bpm
        else:
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
