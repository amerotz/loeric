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

import loeric.core.tune as tu
from loeric.core.contours.base import NotewiseContour, NotewiseContourConfig


class BarLengthContourConfig(NotewiseContourConfig):
    pass


class BarLengthContour(NotewiseContour):
    """A contour holding the length of each note in the tune."""

    config_class = BarLengthContourConfig

    def __init__(self):
        super().__init__()

    def calculate(self, tune: tu.Tune) -> None:
        """Contains the length of the bar each note occupies.

        :param tune: the input tune object.
        """
        super().calculate(tune)

        self._contour = np.empty(self._contour_times.shape)
        # iterate over time signatures
        for i in range(len(tune.time_signatures)):
            ts_1 = tune.time_signatures[i]
            t1 = float(ts_1.time)

            if i < len(tune.time_signatures) - 1:
                t2 = float(tune.time_signatures[i + 1].time)
            else:
                t2 = np.inf

            bar_length = ts_1.eighths_per_bar.eighth_duration

            indexes = np.argwhere(
                (self._contour_times >= t1) & (self._contour_times < t2)
            )

            self._contour[indexes] = bar_length
