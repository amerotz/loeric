import logging

import numpy as np
import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp
from loeric.core.player.analysers.base import Analyser, AnalyserConfig

logger = logging.getLogger(__name__)


class AudioAnalyserConfig(AnalyserConfig):
    """Base config for audio analysers.

    :param updates_per_second: how many times per second the compute step runs.
    :param windows_per_second: how many analysis windows are produced per second.
        Must be <= *updates_per_second*.
    :param samplerate: audio sample rate in Hz.
    """

    updates_per_second: float
    windows_per_second: float
    samplerate: int

    model_config = {"extra": "allow"}

    @pdt.model_validator(mode="after")
    def updates_ge_windows(self) -> "AudioAnalyserConfig":
        """Ensure updates_per_second >= windows_per_second.

        :raises ValueError: if there would be gaps between analysis windows.
        """
        if self.updates_per_second < self.windows_per_second:
            raise ValueError(
                "updates_per_second must be >= windows_per_second "
                "to avoid gaps between analysis windows."
            )
        return self


@lp.readonly("windows_per_second")
@lp.readonly("updates_per_second")
@lp.readonly("type")
class AudioAnalyser(Analyser):
    """Base class for audio analysis functions operating on buffered audio frames.

    Accumulates audio data from a stream callback and triggers a compute step
    at a fixed rate. Subclasses implement :meth:`_compute` to produce a scalar
    control value from the buffer.
    """

    config_class = AudioAnalyserConfig

    def __init__(
        self,
        updates_per_second: float,
        windows_per_second: float,
        samplerate: int,
        **kwargs,
    ):
        """Initialise the audio analysis function.

        :param updates_per_second: how many times per second ``_compute`` is called.
        :param windows_per_second: how many analysis windows per second.
        :param samplerate: audio sample rate in Hz.
        :param kwargs: forwarded to :class:`Analyser`.
        """
        super().__init__(**kwargs)

        self._updates_per_second = updates_per_second
        self._windows_per_second = windows_per_second
        self._samplerate = samplerate
        self._buffer = None
        self._value = 0

        self._window_size = max(1, int(samplerate / windows_per_second))
        self._hop_size = max(1, int(samplerate / updates_per_second))

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
            self._buffer = self._buffer[:, self._hop_size:]

    def reset(self):
        """Clear the internal audio buffer."""
        self._buffer = None

    def _compute(self, buffer):
        """Compute a value from the accumulated buffer.

        Override in subclasses to implement specific analysis logic.

        :param buffer: audio window array of shape ``(channels, window_size)``.
        :return: computed float value. Base implementation always returns 0.
        """
        return 0


class RMSConfig(AudioAnalyserConfig):
    """Config for :class:`RMS`.

    :param controls: list of control names this analyser publishes values to.
    :param responsiveness: exponential smoothing factor in [0, 1].
    """

    controls: list[str]
    responsiveness: float


@lp.expose("_controls", "controls")
@lp.expose("_responsiveness", "responsiveness")
class RMS(AudioAnalyser):
    """Root mean square analyser with exponential smoothing and dynamic normalisation.

    Tracks a smoothed RMS level and normalises it against a running min/max,
    producing a value in [0, 1]. The speed of adaptation is controlled by
    :attr:`responsiveness`.
    """

    config_class = RMSConfig

    def __init__(self, responsiveness: float, controls: list[str], **kwargs):
        """Initialise the RMS analyser.

        :param responsiveness: exponential smoothing factor in [0, 1].
            Higher values track changes faster.
        :param controls: list of control names this analyser publishes values to.
        :param kwargs: forwarded to :class:`AudioAnalyser`.
        """
        super().__init__(**kwargs)

        self._responsiveness = responsiveness
        self._controls = controls
        self._level = 0.0
        self._min_level = None
        self._max_level = None

    def _compute(self, buffer):
        """Compute the normalised RMS level from the accumulated buffer.

        Applies exponential smoothing to the level and running min/max,
        then normalises the result to [0, 1].

        :param buffer: audio window array of shape ``(channels, window_size)``.
        :return: normalised RMS value in [0, 1].
        """
        buffer = np.asarray(buffer, dtype=np.float32)
        new_level = np.sqrt(np.mean(np.square(buffer)))

        alpha = self._responsiveness
        self._level += alpha * (new_level - self._level)
        level = self._level

        if self._min_level is None:
            self._min_level = level
        else:
            self._min_level += alpha * (min(level, self._min_level) - self._min_level)

        if self._max_level is None:
            self._max_level = level
        else:
            self._max_level += alpha * (max(level, self._max_level) - self._max_level)

        diff = self._max_level - self._min_level
        value = 0.0 if diff < 1e-9 else float(np.clip((level - self._min_level) / diff, 0.0, 1.0))

        for c in self._controls:
            logger.info(f"{c}: {value:.2f}")

        return value

    def get(self) -> list[le.ContourValue]:
        """Return the current RMS value mapped to all declared controls.

        :return: list of :class:`~loeric.core.element.ContourValue` events.
        """
        return [
            le.ContourValue(name=c, value=self._value, time=le.PerformanceClock.now())
            for c in self._controls
        ]
