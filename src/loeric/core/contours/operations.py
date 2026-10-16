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

import logging
import math

import numpy as np
from scipy.signal import savgol_filter

from loeric.core.contours.base import (
    LOERICContour,
    OperationContour,
    OperationContourConfig,
)

logger = logging.getLogger(__name__)


class MultiplyOperationContourConfig(OperationContourConfig):
    pass


class MultiplyOperationContour(OperationContour):

    config_class = MultiplyOperationContourConfig

    def _operation(self, contours: list[LOERICContour] = []) -> LOERICContour:
        """Return a new contour that holds the product of the input contours.

        :param contours: the contours to multiply.

        :return: a new contour holding the product of the input contours.
        """
        result = np.ones(len(contours[0]))
        for c in contours:
            result = np.multiply(result, c)

        return result


class DivideOperationContourConfig(OperationContourConfig):
    pass


class DivideOperationContour(OperationContour):

    config_class = DivideOperationContourConfig

    def _operation(self, contours: list[LOERICContour] = []) -> LOERICContour:
        """Return a new contour that holds the quotient between two input contours.

        :param contours: the contours to divide.

        :return: a new contour holding the quotient of the input contours.
        """
        assert len(contours) == 2

        return np.divide(contours[0], contours[1])


class WeightedSumOperationContourConfig(OperationContourConfig):
    weights: list[float]
    normalize: bool = True


class WeightedSumOperationContour(OperationContour):

    config_class = WeightedSumOperationContourConfig

    def __init__(self, contours, weights: list = [], normalize: bool = True):

        assert len(contours) == len(weights)

        self._weights = weights
        self._normalize = normalize

        super().__init__(contours)

    def _operation(self, contours: list[LOERICContour] = []) -> LOERICContour:
        """Return a new contour that holds the weighted sum of the input contours.

        :param contours: the contours to add.
        :param weights: the weight for each contour.
        :param normalize: have the weights sum to 1

        :return: a new contour holding the weighted sum of the input contours.
        """
        size = len(contours)
        weights = np.array(self._weights).astype(float)
        if weights is None:
            weights = np.ones((size, 1))
        else:
            if weights.shape != (size, 1):
                weights = weights.reshape(size, 1)
            indexes = np.argwhere(weights < 0)
            weights = abs(weights)

        if self._normalize:
            weights /= weights.sum()

        result = np.zeros(len(contours[0]))

        stacked_components = np.stack(contours)

        # invert negative ones
        stacked_components[indexes] *= -1
        stacked_components[indexes] += 1

        # weight them
        stacked_components = np.multiply(stacked_components, weights)
        # sum them
        result = stacked_components.sum(axis=0)

        return result


class LinearTransformOperationContourConfig(OperationContourConfig):
    a: float = 1
    b: float = 0


class LinearTransformOperationContour(OperationContour):

    config_class = LinearTransformOperationContourConfig

    def __init__(self, contours, a: float = 1, b: float = 0):

        self._a = a
        self._b = b

        super().__init__(contours)

    def _operation(
        self,
        contours: LOERICContour = None,
    ) -> LOERICContour:
        """Apply a linear transformation of the input contour f(x)= ax + b.

        :param contour: the input contour.
        :param a: the slope.
        :param b: the intercept.

        :return: the linear transformation of the input contour.
        """
        assert len(contours) == 1

        return self._a * contours[0] + self._b


class ClampOperationContourConfig(OperationContourConfig):

    low: float = 0
    high: float = 1


class ClampOperationContour(OperationContour):

    config_class = ClampOperationContourConfig

    def __init__(self, contours, low: float = 0, high: float = 1):

        assert len(contours) == 1

        self._low = low
        self._high = high

        super().__init__(contours)

    def _operation(
        self,
        contours: LOERICContour = None,
    ) -> LOERICContour:
        """Clamp the contour in the given range.

        :param contour: the input contour.
        :param low: the lower limit.
        :param high: the higher limit.

        :return: the clamped input contour.
        """
        return np.clip(contours[0], a_min=self._low, a_max=self._high)


class ShiftOperationContourConfig(OperationContourConfig):

    offset: int = -1


class ShiftOperationContour(OperationContour):

    config_class = ShiftOperationContourConfig

    def __init__(self, contours, offset: int = -1):

        self._offset = offset

        super().__init__(contours)

    def _operation(
        self,
        contours: list[LOERICContour] = None,
    ) -> LOERICContour:
        """Shift the contour by offset.

        :param contour: the input contour.
        :param offset: the offset of the contour, in note indexes.

        :return: the shifted input contour.
        """
        assert len(contours) == 1

        return np.roll(contours[0], self._offset)


class ToMeanOperationContourConfig(OperationContourConfig):

    mean: float = 0.5


class ToMeanOperationContour(OperationContour):

    config_class = ToMeanOperationContourConfig

    def __init__(self, contours, mean: float = 0.5):

        assert len(contours) == 1

        self._mean = mean

        super().__init__(contours)

    def to_mean(
        self,
        contours: list[LOERICContour] = None,
    ) -> LOERICContour:
        """Shift the contour so that it has a specific mean.

        :param contour: the input contour.
        :param mean: the desired mean.

        :return: the shifted input contour.
        """
        return contours[0] - contours[0].mean() + self._mean


class PowerOperationContourConfig(OperationContourConfig):

    exp: float = 1


class PowerOperationContour(OperationContour):

    config_class = PowerOperationContourConfig

    def __init__(self, contours, exp: float = 1):

        assert len(contours) == 1

        self._exp = exp

        super().__init__(contours)

    def power(
        self,
        contours: list[LOERICContour] = None,
    ) -> LOERICContour:
        """Elevate the contour to the specified power.

        :param contour: the input contour.
        :param exp: the exponent.

        :return: the modified input contour.
        """
        return math.pow(contours[0], self._exp)


class SmoothOperationContourConfig(OperationContourConfig):

    window: int = 15


class SmoothOperationContour(OperationContour):

    config_class = SmoothOperationContourConfig

    def __init__(self, contours, window: int = 15):

        assert len(contours) == 1
        self._window = window
        super().__init__(contours)

    def _operation(
        self,
        contours: list[LOERICContour] = None,
    ) -> LOERICContour:
        """Smooth the contour averaging over a given window.

        Uses Savitzky-Golay filterig.

        :param contours: the input contour.

        :return: the modified input contour.
        """
        x = contours[0]
        x = np.pad(x, (self._window, self._window), "mean")
        x = savgol_filter(x, self._window, min(3, self._window - 1))
        x = x[self._window : -self._window]
        return x


class ScaleOperationContourConfig(OperationContourConfig):

    min: float = 0
    max: float = 1


class ScaleOperationContour(OperationContour):

    config_class = ScaleOperationContourConfig

    def __init__(self, contours, min: float = 0, max: float = 1):

        assert len(contours) == 1

        self._min_y = min
        self._max_y = max
        self._min_x = np.min(contours[0].values)
        self._max_x = np.max(contours[0].values)

        super().__init__(contours)

    def _operation(
        self,
        contours: list[LOERICContour] = None,
    ) -> LOERICContour:
        """Scale a contour to cover a specific interval.

        :param contour: the input contour.
        :param min: the minimum value.
        :param max: the maximum value.

        :return: the modified input contour.
        """
        x = contours[0]
        x -= self._min_x
        x /= self._max_x - self._min_x
        return self._min_y + (self._max_y - self._min_y) * x
