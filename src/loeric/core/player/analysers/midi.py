import logging

import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp
from loeric.core.player.analysers.base import Analyser, AnalyserConfig

logger = logging.getLogger(__name__)


class MIDIAnalyserConfig(AnalyserConfig):
    """Base config for MIDI analysers."""
    pass


class MIDILoggerConfig(MIDIAnalyserConfig):
    """Config for :class:`MIDILogger`. No additional fields."""
    pass


class MIDIContourAnalyserConfig(MIDIAnalyserConfig):
    """Config for :class:`MIDIContourAnalyser`.

    :param controls: mapping of control names to MIDI CC numbers (0–127).
    """

    controls: dict[str, int]

    @pdt.field_validator("controls")
    @classmethod
    def valid_cc_numbers(cls, v: dict[str, int]) -> dict[str, int]:
        """Ensure all CC numbers are in the valid MIDI range.

        :raises ValueError: if any CC number is outside 0–127.
        """
        invalid = {k: cc for k, cc in v.items() if not 0 <= cc <= 127}
        if invalid:
            raise ValueError(f"CC numbers must be in 0–127, got: {invalid}")
        return v


class MIDIAnalyser(Analyser):
    """Base class for MIDI analysis functions.

    Subclasses implement :meth:`update` to process incoming MIDI messages
    and accumulate :class:`~loeric.core.element.LOERICElement` events.
    """

    config_class = MIDIAnalyserConfig

    def __init__(self, **kwargs):
        """Initialise the MIDI analyser."""
        super().__init__(**kwargs)
        self._control_events: list[le.LOERICElement] = []

    def update(self, message):
        """Process an incoming MIDI message.

        Events are added to ``self._control_events`` and returned by :meth:`get`.

        :param message: incoming MIDI message.
        """
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the most recently produced control events.

        :return: list of :class:`~loeric.core.element.LOERICElement`.
        """
        return self._control_events


class MIDILogger(MIDIAnalyser):
    """MIDI analyser that logs all incoming messages.

    Produces no control events — used for debugging.
    """

    config_class = MIDILoggerConfig

    def update(self, message):
        """Log the incoming MIDI message.

        :param message: the message to log.
        """
        logger.info(f"{message}")


@lp.expose("_controls", "controls")
class MIDIContourAnalyser(MIDIAnalyser):
    """MIDI analyser that maps CC messages to named contour values.

    Filters non-CC messages. Normalises CC values from [0, 127] to [0, 1]
    and emits :class:`~loeric.core.element.ContourValue` events.
    """

    config_class = MIDIContourAnalyserConfig

    def __init__(self, controls: dict[str, int], **kwargs):
        """Initialise the MIDI contour analyser.

        :param controls: mapping of control names to MIDI CC numbers.
        :param kwargs: forwarded to :class:`MIDIAnalyser`.
        """
        super().__init__(**kwargs)
        self._controls = controls

    def update(self, message):
        """Map an incoming CC message to contour events.

        :param message: the MIDI message to process.
        """
        if not message.is_cc():
            return

        events = []
        for name, cc_number in self._controls.items():
            if message.control == cc_number:
                event = le.ContourValue(
                    name=name,
                    value=message.value / 127.0,
                    time=le.PerformanceClock.now(),
                )
                events.append(event)
                logger.info(f"{event.name}: {event.value:.2f}")

        if events:
            self._control_events = events
