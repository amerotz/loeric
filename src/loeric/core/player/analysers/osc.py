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

import loeric.core.element as le
import loeric.core.paths as lp
from loeric.core.player.analysers.base import Analyser, AnalyserConfig

logger = logging.getLogger(__name__)


class OSCAnalyserConfig(AnalyserConfig):
    """Base config for OSC analysers."""

    pass


class OSCLoggerConfig(OSCAnalyserConfig):
    """Config for :class:`OSCLogger`. No additional fields."""

    pass


class OSCContourAnalyserConfig(OSCAnalyserConfig):
    """Config for :class:`OSCContourAnalyser`.

    :param controls: mapping of control names to OSC addresses.
    """

    controls: dict[str, str]


class OSCAnalyser(Analyser):
    """Base class for OSC analysis functions.

    Subclasses implement :meth:`update` to process incoming OSC messages
    and accumulate :class:`~loeric.core.element.LOERICElement` events.
    """

    config_class = OSCAnalyserConfig

    def __init__(self, **kwargs):
        """Initialise the OSC analyser."""
        super().__init__(**kwargs)
        self._control_events: list[le.LOERICElement] = []

    def update(self, message):
        """Process an incoming OSC message.

        Events are added to ``self._control_events`` and returned by :meth:`get`.

        :param message: incoming OSC message.
        """
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the most recently produced control events.

        :return: list of :class:`~loeric.core.element.LOERICElement`.
        """
        return self._control_events


class OSCLogger(OSCAnalyser):
    """OSC analyser that logs all incoming messages.

    Produces no control events — used for debugging.
    """

    config_class = OSCLoggerConfig

    def update(self, message):
        """Log the incoming OSC message.

        :param message: the message to log.
        """
        if not self._active:
            return
        logger.info(f"{message}")


@lp.expose("_controls", "controls")
class OSCContourAnalyser(OSCAnalyser):
    """OSC analyser that maps control messages to named contour values.

    Emits :class:`~loeric.core.element.ContourValue` events.
    """

    config_class = OSCContourAnalyserConfig

    def __init__(self, controls: dict[str, str], **kwargs):
        """Initialise the OSC contour analyser.

        :param controls: mapping of control names to OSC CC numbers.
        :param kwargs: forwarded to :class:`OSCAnalyser`.
        """
        super().__init__(**kwargs)
        self._controls = controls

    def update(self, message):
        """Map an incoming CC message to contour events.

        :param message: the OSC message to process.
        """
        if not self._active:
            return

        message_address, args = message
        if len(args) != 1:
            return
        message_value = args[0]

        events = []
        for name, address in self._controls.items():
            if message_address == address:
                event = le.ContourValue(
                    name=name,
                    value=message_value,
                    time=le.PerformanceClock.now(),
                )
                events.append(event)
                logger.info(f"{event.name}: {event.value:.2f}")

        if events:
            self._control_events = events
