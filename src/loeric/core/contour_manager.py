import inspect
import logging
from functools import cached_property

import pydantic as pdt

import loeric.core.contours as lc
import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.tune as tu

logger = logging.getLogger(__name__)


class ContourManagerConfig(pdt.BaseModel):

    contours: dict[str, lc.LOERICContourConfig]


@lp.expose("_contours", "contours")
class ContourManager:

    _contours: lc.LOERICContour

    def __init__(self, config: dict, tune: tu.Tune):

        # convert config
        if not isinstance(config, ContourManagerConfig):
            # check each contour
            for c in config:
                # if not already config
                if inspect.isclass(c) and issubclass(config[c], lc.LOERICContourConfig):
                    continue

                config[c] = lc.validate_config(config[c])

            config = ContourManagerConfig(contours=config)

        self._config = config

        # create contours
        self._contours = {}

        # for every contour c
        for c in self._config.contours:
            logger.info(f"Creating {c} contour.")

            # create contour
            self._contours[c] = lc.create_contour(tune, self._config.contours[c])

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
