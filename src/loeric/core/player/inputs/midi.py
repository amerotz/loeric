import logging

import mido

import loeric.core.paths as lp
import loeric.core.player.analysers as la
import loeric.core.player.inputs.base as lib

logger = logging.getLogger(__name__)


class UnknownMIDIPortException(Exception):
    """Raised if the corresponding MIDI port cannot be found."""

    def __init__(self, port: str):
        super().__init__(f"Could not find MIDI port '{port}'.")


class MIDIInputConfig(lib.InputInterfaceConfig):

    port: str


@lp.readonly("port")
class MIDIInput(lib.InputInterface):
    """Input interface for MIDI control change messages.

    Opens a MIDI port and maps incoming CC messages to named control values
    normalised to [0, 1].
    """

    config_class = MIDIInputConfig

    def __init__(self, port: str, analysers: dict, **kwargs):
        """Open a MIDI input port and register the CC callback.

        :param port: name of the MIDI input port to open.
        :param controls: mapping of control names to MIDI CC numbers.
        """
        self._type = "midi"

        try:
            self._midi_in = mido.open_input(port)
        except Exception:
            raise UnknownMIDIPortException(port)
        self._midi_in.callback = self._callback

        super().__init__(analysers)

        for a in self._analysers:
            assert isinstance(
                self._analysers[a], la.MIDIAnalyser
            ), f"Invalid analyser '{a}' (not a MIDI analyser)."

    def reset(self):
        """Close the MIDI input port."""
        self._midi_in.close()
        logger.info("Closed midi input.")
