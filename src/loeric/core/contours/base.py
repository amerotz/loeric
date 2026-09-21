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
from functools import cached_property

import numpy as np
import pydantic as pdt

import loeric.core.element as le
import loeric.core.tune as tu

logger = logging.getLogger(__name__)


class InvalidRecipeError(Exception):
    """Raised if the contour recipe is invalid."""


class ContourConfig(pdt.BaseModel):

    model_config = {"extra": "allow"}


class Contour:
    """A class representing a note-wise intensity conotour."""

    config_class = ContourConfig

    def __init__(self):
        """Initialize the class."""
        self._contour = None
        self._is_real_time = False
        self._last_value = np.nan
        self._last_value_start = np.inf
        self._last_value_end = -np.inf

    def __len__(self):
        """The length of this contour."""
        return len(self._contour)

    @cached_property
    def is_real_time(self):
        return self._is_real_time

    @cached_property
    def values(self):
        """Return all contour values as an array"""
        return self._contour

    def calculate(self, midi: tu.Tune) -> None:
        """Calculate the intensity contour for the given tune.

        :param midi: the input tune.
        """
        self._contour_times = np.array([t.eighth_duration for t in midi.times])

    def _at(self, time: le.TimeDelta | float | int) -> (float, int):
        """Return the contour value and its index at a specific time."""
        t = float(time)
        # searchsorted(side="right") returns the first position where
        # contour_times[pos] > t, so pos-1 is the last position where
        # contour_times[pos] <= t.
        pos = int(np.searchsorted(self._contour_times, t, side="right")) - 1

        if pos < 0:
            # time is before the first event
            return self._contour[0], -1

        return self._contour[pos], pos

    def at(self, time: le.TimeDelta | float | int) -> float:
        """Return the value of the contour at a specific performance time, in eighth notes.

        The value and the time range in which it holds are memorised to allow caching.

        :param time: the queried time.
        """
        # check if we already queried in this interval
        if time >= self._last_value_start and time < self._last_value_end:
            return self._last_value

        value, index = self._at(time)

        # memorise value
        self._last_value = value

        # memorise start timestamp
        if index < 0:
            self._last_value_start = -np.inf
        else:
            self._last_value_start = self._contour_times[index]

        # memorise end timestamp
        if index < len(self._contour_times) - 1:
            self._last_value_end = self._contour_times[index + 1]
        else:
            self._last_value_end = np.inf

        return self._last_value
