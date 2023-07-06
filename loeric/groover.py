import mido
import copy
import numpy as np

import tune as tu
import contour as cnt


class Groover:
    """The class responsible for playback, ornamentation and human interaction."""

    def __init__(
        self,
        tune: tu.Tune,
        midi_channel: int = 0,
        transpose: int = 0,
        random_weight: float = 0,
        apply_savgol: bool = True,
    ):
        """
        Initialize the groover class by setting user-defined parameters and creating the contours.

        :param tune: the tune that will be performed.
        :param midi_channel: the midi output channel for all messages.
        :param transpose: the number of semitones by which to transpose the tune.
        :param random_weight: the weight of the random component in contour generation.
        :param apply_savgol: wether or not to apply savgol filtering in contour generation. True by default (recommended).
        """

        # set parameters
        self._tune = tune
        self._midi_channel = midi_channel
        self._transpose_semitones = transpose

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
        msg = copy.deepcopy(message)

        # change midi channel
        msg.channel = self._midi_channel

        # if it's a note message
        if tu.is_note(msg):
            # transpose note
            msg.note += self._transpose_semitones

        if tu.is_note_on(msg):
            # advance the contours
            self.advance_contours()

            msg.velocity = self._current_velocity

        return [msg]

    @property
    def _current_velocity(self):
        return int(self._contour_values["velocity"] * 127)
