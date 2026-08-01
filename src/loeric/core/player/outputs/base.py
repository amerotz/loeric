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
import multiprocessing as mp

import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp

logger = logging.getLogger(__name__)

# set mp method
mp.set_start_method("spawn", force=True)


class OutputInterfaceConfig(pdt.BaseModel):
    pass


@lp.readonly("active")
@lp.readonly("type")
class OutputInterface:
    """Abstract base for all output interfaces.

    Subclasses represent concrete output modalities (MIDI, visual, data, etc.)
    and expose a uniform :meth:`play_events` / :meth:`set` / :meth:`reset` /
    :meth:`done` interface to the player.
    """

    config_class = OutputInterfaceConfig

    def __init__(self):
        """Initialise the output interface."""
        self._contour_values = {}
        self._type = "uninitialised"

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Send a list of events to the output at the given tick.

        :param events: list of :class:`~loeric.core.element.LOERICElement` to send.
        :param tick: current playback position as a :class:`~loeric.core.element.TimeDelta` or float.
        """
        pass

    def reset(self):
        """Reset the output to its initial state, releasing any held resources."""
        pass

    def set(self, inputs: list[le.LOERICElement]):
        """Update the internal contour value store.

        :param contour_values: mapping of contour names to their current float values.
        """
        for i in inputs:
            if isinstance(i, le.ContourValue):
                self._contour_values[i.name] = i.value

    def done(self) -> bool:
        """Return whether all pending output has been flushed.

        :return: ``True`` if the output queue is empty and the interface is idle.
        """
        return True
