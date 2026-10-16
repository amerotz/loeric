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


class IntensityContourConfig(NotewiseContourConfig):

    weights: list = None
    savgol: bool = True
    shift: bool = False
    scale: bool = False


class IntensityContour(NotewiseContour):
    """A contour given by the weighted sum of O'Canainn components."""

    config_class = IntensityContourConfig

    def __init__(
        self,
        weights: list = None,
        savgol: bool = True,
        shift: bool = False,
        scale: bool = False,
    ):
        super().__init__()
        self._weights = weights
        self._savgol = savgol
        self._shift = shift
        self._scale = scale

    def calculate(
        self,
        tune: tu.Tune,
    ) -> None:
        """Compute the contour as the weighted sum of O'Canainn component.

        :param tune: the input tune.
        :param weights: the weights for the components
        :param savgol: apply a final savgol filtering step
        :param shift: bring the mean of the array close to 0.5.

        """
        super().calculate(tune)

        weights = np.array(self._weights).astype(float)

        # calculate the components
        components = self.ocanainn_scores(tune)
        # stack them
        stacked_components = np.stack(components, axis=0)
        size = stacked_components.shape[0]

        if weights is None:
            weights = np.ones((size, 1)) / size
        else:
            if weights.shape != (size, 1):
                weights = weights.reshape(size, 1)
            indexes = np.argwhere(weights < 0)
            weights = abs(weights)
            weights /= weights.sum()

        # weight them
        stacked_components[indexes] *= -1
        stacked_components[indexes] += 1
        stacked_components = np.multiply(stacked_components, weights)
        # sum them
        stacked_components = stacked_components.sum(axis=0)

        self._contour = stacked_components

        # savgol filtering
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

    def ocanainn_scores(
        self, tune: tu.Tune
    ) -> tuple[np.array, np.array, np.array, np.array, np.array]:
        """Compute the individual components for the ocanainn score.

        These are:
        * frequency score;
        * beat score;
        * ambitus score;
        * leap score;
        * length score.

        :param tune: the input tune used to compute the individual scores.

        :return: the computed scores
        """
        pitches = tune.pitches
        durations = tune.durations

        # o canainn score
        notes = pitches % 12

        # frequency score
        values, counts = np.unique(notes, return_counts=True)
        frequency_score = np.array(
            [counts[np.where(values == n)] for n in notes]
        ).astype(float)
        frequency_score = frequency_score.reshape(-1)
        frequency_score = np.interp(
            frequency_score, (frequency_score.min(), frequency_score.max()), (0, 1)
        )

        # strong beat
        indexes = np.where(
            self._contour_times
            % (
                # TODO make this keep track of time signatures
                tune.time_signatures[0].eighths_per_bar.eighth_duration
                / tune.time_signatures[0].beat_count
            )
            == 0
        )
        beats = -np.ones(notes.shape)
        beats[indexes] = notes[indexes]
        values, counts = np.unique(beats, return_counts=True)
        beat_score = np.array([counts[np.where(values == n)] for n in beats]).astype(
            float
        )
        beat_score = beat_score.reshape(-1)
        beat_score[np.where(beats == -1)] = 0
        beat_score = beat_score.reshape(-1)
        beat_score = np.interp(beat_score, (beat_score.min(), beat_score.max()), (0, 1))

        # highest/lowest score
        highest = pitches == max(pitches)
        lowest = pitches == min(pitches)
        ambitus_score = (highest | lowest).astype(float)

        # leap score
        diff = np.diff(pitches)
        diff = np.insert(diff, 0, 0)
        leaps = -np.ones(pitches.shape)
        index = np.where(diff >= 7)
        leaps[index] = notes[index]
        values, counts = np.unique(leaps, return_counts=True)
        leap_score = np.array([counts[np.where(values == n)] for n in leaps]).astype(
            float
        )
        leap_score = leap_score.reshape(-1)
        leap_score[np.where(leaps == -1)] = 0
        if leap_score.min() != leap_score.max():
            leap_score = np.interp(
                leap_score, (leap_score.min(), leap_score.max()), (0, 1)
            )

        # long score
        values, counts = np.unique(durations, return_counts=True)
        index = np.argmax(counts)
        val = values[index]
        length_score = (durations > val).astype(float)

        return frequency_score, beat_score, ambitus_score, leap_score, length_score
