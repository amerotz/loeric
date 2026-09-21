import logging
from functools import cached_property

import loeric.core.contours as lc
import loeric.core.element as le
import loeric.core.tune as tu

logger = logging.getLogger(__name__)


class ContourManager:
    def __init__(self, config: dict, tune: tu.Tune):

        self._config = config

        # create contours
        self._contours = {}

        # for every contour c
        for c in self._config:
            logger.info(f"Creating {c} contour.")

            # create contour
            self._contours[c] = lc.create_contour(
                tune, self._config[c]["recipe"], parent=c
            )

    def __setitem__(self, key: str, value: float):
        """Set the contour named ``key`` to ``value``."""

    def __getitem__(self, key: str):
        """Get the value of contour named ``key``."""

    @cached_property
    def contours(self):
        """Return a dictionary of all contours."""
        return self._contours

    def at(self, time: le.TimeDelta):
        """Return contour values at a specific time."""
        events = []
        for c in self._contours:
            events.append(
                le.ContourValue(name=c, value=self._contours[c].at(time), time=time)
            )
        return events

    def reset(self):
        """Reset all variables."""
