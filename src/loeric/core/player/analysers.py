import logging

import numpy as np

import loeric.core.element as le
import loeric.core.paths as lp

logger = logging.getLogger(__name__)


class Analyser:
    """Defines how to analyse a given input."""

    def __init__(self, type: str, **kwargs):
        """Initialise the analyser."""
        self._type = type

    def update(self, x):
        """Update the internal status with the new input."""
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the result of the last update step."""
        return []

    @staticmethod
    def create_function(config: dict, samplerate: int = None):
        """Instantiate the appropriate analysis function from a config dict.

        :param config: function configuration. Must contain a ``type`` key.
        :return: an :class:`AudioAnalyser` subclass instance.
        :raises ValueError: if ``config["type"]`` is not recognised.
        """
        if config["type"] == "rms":
            return RMS(**config, samplerate=samplerate)
        elif config["type"] == "midi_cc":
            return MIDIContourAnalyser(**config)
        elif config["type"] == "midi_logger":
            return MIDILogger(**config)
        else:
            raise ValueError(f"Unknown analyser type {config['type']}.")


class MIDIAnalyser(Analyser):
    """Base class for MIDI analysis functions operating on MIDI messages.

    Subclasses implement :meth:`update` to produce
    control events from incoming messages.
    """

    def __init__(self, **kwargs):

        super().__init__(**kwargs)
        self._control_events = []

    def update(self, message):
        """Process the incoming message.

        Events are added to ``self._control_events`` and returned by :meth`get`.
        """
        pass

    def get(self):
        return self._control_events


class MIDILogger(MIDIAnalyser):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def update(self, message):
        """Log the MIDI message.

        :param message: the message to log.
        """
        logger.info(f"{message}")


@lp.expose("_controls", "controls")
class MIDIContourAnalyser(MIDIAnalyser):

    _controls: dict[str, int]

    def __init__(self, controls: dict[str, int], **kwargs):
        super().__init__(**kwargs)
        self._controls = controls

    def update(self, message):
        """Build the MIDI message callback for the given control mapping.

        Filters non-CC messages. Normalises CC values to [0, 1]
        and maps them to controls.

        :param message: the message to analyse.
        """
        events = []
        if not message.is_cc:
            return
        for c in self._controls:
            if message.control == self._controls[c]:
                event = le.ContourValue(
                    name=c,
                    value=message.value / 127.0,
                    time=le.PerformanceClock.now(),
                )
                events.append(event)
                logger.info(f"{event.name}: {event.value}")

        # only update if we got something new
        # otherwise keep the old ones
        if len(events) != 0:
            self._control_events = events


@lp.readonly("windows_per_second")
@lp.readonly("updates_per_second")
@lp.readonly("type")
class AudioAnalyser(Analyser):
    """Base class for audio analysis functions operating on buffered audio frames.

    Accumulates audio data from a stream callback and triggers a compute step
    at a fixed rate. Subclasses implement :meth:`_compute` to produce a scalar
    control value from the buffer.
    """

    def __init__(
        self,
        updates_per_second: float,
        windows_per_second: float,
        samplerate: int,
        **kwargs,
    ):
        """Initialise the audio analysis function.

        :param type: identifier string for the function type.
        :param updates_per_second: how many times per second ``_compute`` is called.
        """
        super().__init__(**kwargs)

        self._buffer = None
        self._value = 0
        self._last_update = 0
        self._updates_per_second = updates_per_second
        self._windows_per_second = windows_per_second
        self._samplerate = samplerate

        # window length
        self._window_size = max(
            1,
            int(samplerate / windows_per_second),
        )

        # hop length
        self._hop_size = max(
            1,
            int(samplerate / updates_per_second),
        )

        if self._hop_size > self._window_size:
            raise ValueError(
                "updates_per_second must be >= windows_per_second "
                "to avoid gaps between analysis windows."
            )

    def update(self, indata):
        """Accumulate incoming audio data and trigger a compute step when due.

        :param indata: audio frame array from the sounddevice callback,
            shape ``(frames, channels)``.
        """
        chunk = np.asarray(indata, dtype=np.float32).T.copy()

        if self._buffer is None:
            self._buffer = chunk
        else:
            self._buffer = np.concatenate((self._buffer, chunk), axis=1)

        if self._buffer.shape[1] >= self._window_size:
            window = self._buffer[:, : self._window_size]

            self._value = self._compute(window)

            # Slide forward by hop size
            self._buffer = self._buffer[:, self._hop_size :]

    def reset(self):
        """Clear the internal audio buffer."""
        self._buffer = None

    def _compute(self, buffer):
        """Compute a value from the accumulated buffer.

        Override in subclasses to implement specific analysis logic.

        :return: computed float value. Base implementation always returns 0.
        """
        return 0


@lp.expose("_controls", "controls")
@lp.expose("_responsiveness", "responsiveness")
class RMS(AudioAnalyser):
    """Root mean square analyser with exponential smoothing and dynamic normalisation.

    Tracks a smoothed RMS level and normalises it against a running min/max,
    producing a value in [0, 1]. The speed of adaptation is controlled by
    :attr:`responsiveness`.

    This is the original implementation from the first LOERIC version.
    """

    _controls: list[str]
    _responsiveness: float

    def __init__(
        self,
        responsiveness: float,
        controls: list,
        **kwargs,
    ):
        """Initialise the RMS analyser.

        :param responsiveness: exponential smoothing factor in [0, 1].
            Higher values track changes faster.
        :param controls: list of control names this analyser publishes values to.
        :param kwargs: passed to :class:`AudioAnalyser`.
        """
        super().__init__(**kwargs)

        self._responsiveness = responsiveness
        self._controls = controls

        self._level = 0.0
        self._min_level = None
        self._max_level = None

    def _compute(self, buffer):
        """Compute the normalised RMS level from the accumulated buffer.

        Applies exponential smoothing to the level and to the running min/max,
        then normalises the result to [0, 1].

        :return: normalised RMS value in [0, 1], or 0.0 if the buffer is empty.
        """
        if self._buffer is None or self._buffer.size == 0:
            return 0.0

        # RMS level
        buffer = np.asarray(buffer, dtype=np.float32)
        new_level = np.sqrt(np.mean(np.square(buffer)))

        # smoothing
        alpha = self._responsiveness
        self._level += alpha * (new_level - self._level)
        level = self._level

        # minimum
        if self._min_level is None:
            self._min_level = level
        else:
            self._min_level += alpha * (min(level, self._min_level) - self._min_level)

        # maximum
        if self._max_level is None:
            self._max_level = level
        else:
            self._max_level += alpha * (max(level, self._max_level) - self._max_level)

        # normalise
        diff = self._max_level - self._min_level
        if diff < 1e-9:
            value = 0.0
        else:
            value = np.clip(
                (level - self._min_level) / diff,
                0.0,
                1.0,
            )

        for c in self._controls:
            logger.info(f"{c}: {value:.2f}")

        return float(value)

    def get(self):
        """Return the current RMS value mapped to all declared controls.

        :return: list of control events.
        """
        return [
            le.ContourValue(name=c, value=self._value, time=le.PerformanceClock.now())
            for c in self._controls
        ]
