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

import time
from typing import Literal

import numpy as np


class Parameter:
    """A parameter that can be used by the mapper.

    Supports division in multiple ranges.
    """

    __slots__ = (
        "_name",
        "_min_value",
        "_max_value",
        "_value",
        "_update_timestamp",
        "_default_min",
        "_default_max",
    )

    def __init__(
        self,
        name,
        min_value=-np.inf,
        max_value=np.inf,
        mode: Literal["select"] | Literal["clip"] = "select",
    ):
        self._name = name
        self._update_timestamp = np.inf

        self._min_value, self._max_value = np.round(min_value, 2).astype(
            float
        ), np.round(max_value, 2).astype(float)

        self._value = np.nan

        assert mode in ["select", "clip"]

        if mode == "select":
            self._default_min = np.nan
            self._default_max = np.nan
        else:
            self._default_min = self._min_value
            self._default_max = self._max_value

    def has_changed_since(self, timestamp):
        """Check if the parameter has been updated since a timestamp."""
        return self._update_timestamp >= timestamp

    def set(self, value, bypass_range=False):
        """Set the parameter.

        Optionally bypass range checks.
        """
        old_value = self._value

        self._value = value

        if not bypass_range:
            # clip or nan the extremes
            if value > self._max_value:
                self._value = self._default_max
            elif value < self._min_value:
                self._value = self._default_min

        if self._value != old_value:
            self._update_timestamp = time.time()

    def get(self):
        """Get the parameter value, optionally a dict with value for every range where it fits, otherwise 0."""
        return self._value

    def reset(self):
        self._value = np.nan

    def __repr__(self):
        return f"(Param '{self._name}' v={self._value}, r=[{self._min_value},{self._max_value}]"

    @staticmethod
    def basename(x: str):
        return x.split("@")[0].replace("$", "").replace("%", "")
