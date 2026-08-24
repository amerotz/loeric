import numpy as np


class Parameter:
    """A parameter that can be used by the mapper.

    Supports division in multiple ranges.
    """

    __slots__ = ("_name", "_min_value", "_max_value", "_value")

    def __init__(self, name, min_value=-np.inf, max_value=np.inf):
        self._name = name

        self._min_value, self._max_value = np.round(min_value, 2).astype(
            float
        ), np.round(max_value, 2).astype(float)

        self._value = np.nan

    def set(self, value):
        """Set the parameter."""
        if value >= self._min_value and value <= self._max_value:
            self._value = value
        else:
            self._value = np.nan

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
