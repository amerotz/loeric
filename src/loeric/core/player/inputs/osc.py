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
import threading

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

import loeric.core.paths as lp
import loeric.core.player.analysers as la
import loeric.core.player.inputs.base as lib

logger = logging.getLogger(__name__)


class OSCInputConfig(lib.InputInterfaceConfig):

    server: str
    port: int


@lp.readonly("server")
@lp.readonly("port")
class OSCInput(lib.InputInterface):
    """Input interface for OSC control change messages.

    Opens a OSC port and maps incoming CC messages to named control values
    normalised to [0, 1].
    """

    config_class = OSCInputConfig

    def __init__(self, server: str, port: int, **kwargs):
        """Open a OSC input port and register the CC callback.

        :param port: name of the OSC input port to open.
        :param controls: mapping of control names to OSC CC numbers.
        """
        self._server = server
        self._port = port

        if kwargs["active"]:
            self._dispatcher = Dispatcher()
            self._dispatcher.set_default_handler(self._callback)

            # create the server
            self._osc_input = BlockingOSCUDPServer(
                (self._server, self._port), self._dispatcher
            )

            # start it in a thread
            self._thread = threading.Thread(target=self._osc_input.serve_forever)
            self._thread.daemon = True
            self._thread.start()

        super().__init__(**kwargs)

        for a in self._analysers:
            assert isinstance(
                self._analysers[a], la.OSCAnalyser
            ), f"Invalid analyser '{a}' (not a OSC analyser)."

    def _callback(self, address, *message, **args):
        """Update all analysers with the new input.

        Override base function to support OSC message bundles.
        """
        for a in self._analysers:
            self._analysers[a].update((address, message))

    def reset(self):
        """Close the OSC input port."""
        if not self._active:
            return

        # close the server
        self._osc_input.shutdown()

        # wait for thread
        if self._thread.is_alive():
            self._thread.join(timeout=2)

        self._osc_input.server_close()
        logger.info("Closed OSC input.")
