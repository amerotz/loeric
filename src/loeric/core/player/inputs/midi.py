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
from typing import Literal

import mido

import loeric.core.paths as lp
import loeric.core.player.inputs.analysers as la
import loeric.core.player.inputs.base as lib

logger = logging.getLogger(__name__)


class MIDIInputConfig(lib.InputInterfaceConfig):

    type: Literal["midi"]
    port: str


@lp.readonly("port")
class MIDIInput(lib.InputInterface):
    """Input interface for MIDI control change messages.

    Opens a MIDI port and maps incoming CC messages to named control values
    normalised to [0, 1].
    """

    config_class = MIDIInputConfig

    def __init__(self, port: str, **kwargs):
        """Open a MIDI input port and register the CC callback.

        :param port: name of the MIDI input port to open.
        :param controls: mapping of control names to MIDI CC numbers.
        """
        self._port = port

        if kwargs["active"]:

            virtual = self._port not in mido.get_input_names()
            if virtual:
                logger.warning(
                    f"No MIDI port '{self._port}' available. Creating a virtual one."
                )
            self._midi_in = mido.open_input(self._port, virtual=virtual)
            self._midi_in.callback = self._callback

        super().__init__(**kwargs)

        for a in self._analysers:
            assert isinstance(
                self._analysers[a], la.MIDIAnalyser
            ), f"Invalid analyser '{a}' (not a MIDI analyser)."

    def reset(self):
        """Close the MIDI input port."""
        if not self._active:
            return
        self._midi_in.close()
        logger.info("Closed midi input.")
