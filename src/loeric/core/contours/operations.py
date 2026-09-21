import logging
import math

import numpy as np
from scipy.signal import savgol_filter

from loeric.core.contours.base import Contour

logger = logging.getLogger(__name__)


"""
class OperationContourConfig(pdt.BaseModel):

    contours: list["OperationContourConfig" | ContourConfig]
"""


class OperationContour(Contour):
    """A contour holding an aggregation of other contours."""

    # config_class = OperationContourConfig

    def __init__(self, contours):

        super().__init__()

        self._member_contours = contours
        self._contour = self._operation([c._contour for c in self._member_contours])
        self._contour_times = contours[0]._contour_times
        self._is_real_time = np.any([c.is_real_time for c in self._member_contours])

    def _at(self, time):
        if self.is_real_time:

            # retrieve the at value of every member
            values = [[c.at(time)] for c in self._member_contours]
            values = np.array(values)
            # values = np.nan_to_num(values, nan=0.5)

            # aggregate
            res = self._operation(values)

            if np.isnan(res[0]):
                logger.error(self._operation)
                raise Exception

            t = float(time)
            pos = int(np.searchsorted(self._contour_times, t, side="right")) - 1
            index = -1 if pos < 0 else pos

            return res[0], index
        else:
            return super()._at(time)

    def _operation(self, contours: list[Contour] = []) -> Contour:
        return None


class MultiplyOperationContour(OperationContour):

    def _operation(self, contours: list[Contour] = []) -> Contour:
        """Return a new contour that holds the product of the input contours.

        :param contours: the contours to multiply.

        :return: a new contour holding the product of the input contours.
        """
        result = np.ones(len(contours[0]))
        for c in contours:
            result = np.multiply(result, c)

        return result


class DivideOperationContour(OperationContour):
    def _operation(self, contours: list[Contour] = []) -> Contour:
        """Return a new contour that holds the quotient between two input contours.

        :param contours: the contours to divide.

        :return: a new contour holding the quotient of the input contours.
        """
        assert len(contours) == 2

        return np.divide(contours[0], contours[1])


class WeightedSumOperationContour(OperationContour):

    def __init__(self, contours, weights: list = [], normalize: bool = True):

        assert len(contours) == len(weights)

        self._weights = weights
        self._normalize = normalize

        super().__init__(contours)

    def _operation(self, contours: list[Contour] = []) -> Contour:
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


class LinearTransformOperationContour(OperationContour):

    def __init__(self, contours, a: float = 1, b: float = 0):

        self._a = a
        self._b = b

        super().__init__(contours)

    def _operation(
        self,
        contours: Contour = None,
    ) -> Contour:
        """Apply a linear transformation of the input contour f(x)= ax + b.

        :param contour: the input contour.
        :param a: the slope.
        :param b: the intercept.

        :return: the linear transformation of the input contour.
        """
        assert len(contours) == 1

        return self._a * contours[0] + self._b


class ClampOperationContour(OperationContour):

    def __init__(self, contours, low: float = 0, high: float = 1):

        assert len(contours) == 1

        self._low = low
        self._high = high

        super().__init__(contours)

    def _operation(
        self,
        contours: Contour = None,
    ) -> Contour:
        """Clamp the contour in the given range.

        :param contour: the input contour.
        :param low: the lower limit.
        :param high: the higher limit.

        :return: the clamped input contour.
        """
        return np.clip(contours[0], a_min=self._low, a_max=self._high)


class ShiftOperationContour(OperationContour):

    def __init__(self, contours, offset: int = -1):

        self._offset = offset

        super().__init__(contours)

    def _operation(
        self,
        contours: list[Contour] = None,
    ) -> Contour:
        """Shift the contour by offset.

        :param contour: the input contour.
        :param offset: the offset of the contour, in note indexes.

        :return: the shifted input contour.
        """
        assert len(contours) == 1

        return np.roll(contours[0], self._offset)


class ToMeanOperationContour(OperationContour):

    def __init__(self, contours, mean: float = 0.5):

        assert len(contours) == 1

        self._mean = mean

        super().__init__(contours)

    def to_mean(
        self,
        contours: list[Contour] = None,
    ) -> Contour:
        """Shift the contour so that it has a specific mean.

        :param contour: the input contour.
        :param mean: the desired mean.

        :return: the shifted input contour.
        """
        return contours[0] - contours[0].mean() + self._mean


class PowerOperationContour(OperationContour):

    def __init__(self, contours, exp: float = 1):

        assert len(contours) == 1

        self._exp = exp

        super().__init__(contours)

    def power(
        self,
        contours: list[Contour] = None,
    ) -> Contour:
        """Elevate the contour to the specified power.

        :param contour: the input contour.
        :param exp: the exponent.

        :return: the modified input contour.
        """
        return math.pow(contours[0], self._exp)


class SmoothOperationContour(OperationContour):

    def __init__(self, contours, window: float = 15):

        assert len(contours) == 1
        self._window = window
        super().__init__(contours)

    def smooth(
        self,
        contours: list[Contour] = None,
    ) -> Contour:
        """Elevate the contour to the specified power.

        :param contour: the input contour.
        :param exp: the exponent.

        :return: the modified input contour.
        """
        x = contours[0]
        x = np.pad(x, (self._window, self._window), "mean")
        x = savgol_filter(x, self._window, min(3, self._window - 1))
        x = x[self._window : -self._window]
        return x


class ScaleOperationContour(OperationContour):

    def __init__(self, contours, min: float = 0, max: float = 1):

        assert len(contours) == 1

        self._min_y = min
        self._max_y = max
        self._min_x = np.min(contours[0].values)
        self._max_x = np.max(contours[0].values)

        super().__init__(contours)

    def _operation(
        self,
        contours: list[Contour] = None,
    ) -> Contour:
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
