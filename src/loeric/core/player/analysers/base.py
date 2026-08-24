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

import pydantic as pdt

import loeric.core.element as le

logger = logging.getLogger(__name__)


class AnalyserConfig(pdt.BaseModel):
    """Base config for all analysers.

    :param type: analyser type string used by the registry.
    """

    type: str
    active: bool
    model_config = {"extra": "allow"}


class Analyser:
    """Base class for all input analysers.

    Subclasses implement :meth:`update` to consume incoming data and
    :meth:`get` to return the resulting :class:`~loeric.core.element.LOERICElement` list.
    """

    config_class: type[AnalyserConfig] = AnalyserConfig

    def __init__(self, type: str, active: bool):
        """Initialise the analyser.

        :param type: analyser type identifier.
        """
        self._type = type
        self._active = active

    def update(self, x):
        """Update the internal state with new input data.

        :param x: incoming data (audio frame or MIDI message depending on subclass).
        """
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the result of the last update step.

        :return: list of :class:`~loeric.core.element.LOERICElement` produced since last call.
        """
        return []

    def reset(self):
        """Reset internal state."""
        pass
