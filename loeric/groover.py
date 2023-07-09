import mido
import copy
import random
import numpy as np

import tune as tu
import contour as cnt

TEMPO_WARP = 0.1
CUT = "cut"
CUT_CHANCE = 0.5


class Groover:
    """The class responsible for playback, ornamentation and human interaction."""

    def __init__(
        self,
        tune: tu.Tune,
        bpm: int = None,
        midi_channel: int = 0,
        transpose: int = 0,
        random_weight: float = 0,
        apply_savgol: bool = True,
    ):
        """
        Initialize the groover class by setting user-defined parameters and creating the contours.

        :param tune: the tune that will be performed.
        :param bpm : the user-defined tempo in bpm for the tune.
        :param midi_channel: the midi output channel for all messages.
        :param transpose: the number of semitones by which to transpose the tune.
        :param random_weight: the weight of the random component in contour generation.
        :param apply_savgol: whether or not to apply savgol filtering in contour generation. True by default (recommended).
        """

        # set parameters
        self._tune = tune
        if bpm is None:
            self._user_tempo = self._tune.tempo
        else:
            self._user_tempo = mido.bpm2tempo(bpm)
        self._midi_channel = midi_channel
        self._transpose_semitones = transpose

        # offset for messages after ornaments
        self._offset = 0
        # create contours
        self._contours = {}

        # velocity contour
        self._contours["velocity"] = cnt.IntensityContour()
        self._contours["velocity"].calculate(
            self._tune,
            weights=np.array([0.2, 0.3, 0.1, 0.2, 0.2]),
            random_weight=random_weight,
            savgol=apply_savgol,
        )
        # tempo contour
        self._contours["tempo"] = cnt.IntensityContour()
        self._contours["tempo"].calculate(
            self._tune,
            weights=np.array([0.25, 0.1, 0.3, 0.25, 0.1]),
            random_weight=random_weight,
            savgol=apply_savgol,
        )
        # ornament contour
        self._contours["ornament"] = cnt.IntensityContour()
        self._contours["ornament"].calculate(
            self._tune,
            weights=np.array([0.2, 0.35, 0.15, 0.15, 0.2]),
            random_weight=random_weight,
            savgol=apply_savgol,
        )

        # object holding each contour's value in a given moment
        self._contour_values = {}

    @classmethod
    def from_config(cls, config_file: str):
        """
        Initialize the groover class by using a configuration file.

        :param config_file: the configuration file (must be a JSON file).
        """
        # TODO
        pass

    def advance_contours(self) -> None:
        """
        Retrieve the next value of each contour and store it for future use.
        """

        for contour_name in self._contours:
            self._contour_values[contour_name] = self._contours[contour_name].next()

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
        if ornament_type == CUT:
            # generate a cut
            cut = copy.deepcopy(message)
            cut_index = self._tune.semitones_from_tonic(message.note)
            cut.note = tu.above_approach_scale[cut_index] + message.note
            duration = self._tune.beat_duration / 24
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
        return ornaments

    def choose_ornament(self, message: mido.Message) -> str:
        """
        Evaluate the ornament specific rules and chooose how the note will be ornamented.

        :param message: the midi message to ornament.

        :return: the chosen ornament type.
        """
        options = []

        is_beat = self._tune.is_on_a_beat()
        if is_beat and random.uniform(0, 1) < CUT_CHANCE:
            options.append(CUT)

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

        :param message: the input time value in seconds, given the original tempo.

        :return: the new duration of the input time value in seconds.
        """
        tempo_ratio = self._current_tempo / self._tune.tempo
        return tempo_ratio * time

    @property
    def _current_tempo(self) -> int:
        """
        :return: the current tempo given the value of the tempo contour.
        """
        value = int(
            2 * TEMPO_WARP * self._user_tempo * (self._contour_values["tempo"] - 0.5)
        )
        return self._user_tempo + value

    @property
    def _current_velocity(self) -> int:
        """
        :return: the current velocity given the value of the velocity contour.
        """
        value = int(self._contour_values["velocity"] * 127)
        if self._tune.is_on_a_beat():
            value += 16

        # clamp velocity
        value = max(min(value, 127), 0)
        return value
