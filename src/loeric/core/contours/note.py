# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.

import numpy as np
from scipy.signal import savgol_filter

import loeric.core.tune as tu
from loeric.core.contours.base import NotewiseContour, NotewiseContourConfig


class PitchContourConfig(NotewiseContourConfig):
    pass


class PitchContour(NotewiseContour):
    """A contour holding the pitch of notes in the tune."""

    config_class = PitchContourConfig

    def __init__(
        self,
        savgol: bool = True,
        shift: bool = True,
        scale: bool = True,
    ):

        super().__init__()
        self._savgol = savgol
        self._shift = shift
        self._scale = scale

    def calculate(
        self,
        tune: tu.Tune,
    ) -> None:

        super().calculate(tune)

        self._contour = tune.pitches

        if self._savgol or self._shift or self._scale:
            self._contour = self.scale_and_savgol(
                self._contour, savgol=self._savgol, shift=self._shift, scale=self._scale
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


class DurationContourConfig(NotewiseContourConfig):

    absolute: bool


class DurationContour(NotewiseContour):
    """A contour holding the length of each note in the tune."""

    config_class = DurationContourConfig

    def __init__(self, absolute: bool):
        super().__init__()
        self._absolute = absolute

    def calculate(self, tune: tu.Tune) -> None:
        """Contains the duration of each note.

        :param tune: the input tune object.
        """
        super().calculate(tune)

        self._contour = tune.float_durations
        if self._absolute:
            self._contour = 8 / self._contour
