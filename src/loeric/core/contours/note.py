import numpy as np
from scipy.signal import savgol_filter

import loeric.core.tune as tu
from loeric.core.contours.base import Contour, ContourConfig


class PitchContourConfig(ContourConfig):
    pass


class PitchContour(Contour):
    """A contour holding the pitch of notes in the tune."""

    config_class = PitchContourConfig

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tu.Tune,
        savgol: bool = True,
        shift: bool = True,
        scale: bool = True,
    ) -> None:

        super().calculate(midi)

        self._contour = midi.pitches

        if savgol or shift or scale:
            self._contour = self.scale_and_savgol(
                self._contour, savgol=savgol, shift=shift, scale=scale
            )

    def scale_and_savgol(
        self, array: np.ndarray, savgol: bool = True, shift: bool = False, scale=False
    ) -> np.ndarray:
        """Scale the contour to have it range between 0 and 1.

        Optionally, apply a Savitzky-Golay filter with a window of 15 and order 3.
        Optionally, rescale the array to bring the extremes to 0 and 1.
        Optionally, shift the array to bring its mean closer to 0.5.

        :param array: the input contour.
        :param savgol: apply the savgol filter.
        :param scale: rescale the array to use the full range.
        :param shift: shift the filtered array so that its mean is close to 0.5.

        :return: the processed array.
        """
        # this is a mandatory scaling step, since the contour needs
        # to have range 0 to 1
        array -= min(array)
        array /= max(array)

        if savgol:
            window = 15
            array = np.pad(array, (window, window), "mean")
            array = savgol_filter(array, window, 3)
            array = array[window:-window]

        if scale:
            array -= min(array)
            array /= max(array)

        if shift:
            array /= 2 * array.mean()

        array[array < 0] = 0
        array[array > 1] = 1

        return array


class DurationContour(Contour):
    """A contour holding the length of each note in the tune."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tu.Tune, absolute: bool) -> None:
        """Contains the duration of each note.

        :param midi: the input tune object.
        """
        super().calculate(midi)

        self._contour = midi.float_durations
        if absolute:
            self._contour = 8 / self._contour
