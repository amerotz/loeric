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


import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.analysers as la


class InputInterfaceConfig(pdt.BaseModel):

    active: bool
    analysers: dict[str, la.AnalyserConfig]
    model_config = {"extra": "allow"}


@lp.readonly("active")
@lp.readonly("type")
@lp.expose("_analysers", "analysers")
class InputInterface:
    """Abstract base for all input interfaces.

    Subclasses represent concrete input modalities (MIDI, audio, etc.) and
    expose a uniform :meth:`get` / :meth:`reset` interface to the player.
    """

    config_class = InputInterfaceConfig

    def __init__(self, analysers: dict, type: str, active: bool):
        """Initialise the input interface."""
        self._type = type
        self._active = active

        self._analysers = {
            a: la.create_analyser(
                analysers[a],
                samplerate=self._samplerate if hasattr(self, "_samplerate") else None,
                active=active,
            )
            for a in analysers
        }

    def _callback(self, x, **args):
        """Update all analysers with the new input."""
        for a in self._analysers:
            self._analysers[a].update(x)

    def reset(self):
        """Reset the interface state."""
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the merged control events from all active analysers.

        :return: a list of events.
        """
        if not self._active:
            return []
        events = []
        for a in self._analysers:
            events.extend(self._analysers[a].get())
        return events


class UnknownMIDIPortException(Exception):
    """Raised if the corresponding MIDI port cannot be found."""

    def __init__(self, port: str):
        super().__init__(f"Could not find MIDI port '{port}'.")
