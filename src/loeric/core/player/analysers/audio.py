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

import librosa
import numpy as np
import pydantic as pdt
from scipy.signal import butter, sosfilt

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
        if not self._active:
            return
        chunk = np.asarray(indata, dtype=np.float32).T.copy()

        if self._buffer is None:
            self._buffer = chunk
        else:
            self._buffer = np.concatenate((self._buffer, chunk), axis=1)

        if self._buffer.shape[1] >= self._window_size:
            window = self._buffer[:, : self._window_size]
            self._value = self._compute(window)
            self._buffer = self._buffer[:, self._hop_size :]

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
        value = (
            0.0
            if diff < 1e-9
            else float(np.clip((level - self._min_level) / diff, 0.0, 1.0))
        )

        """
        for c in self._controls:
            logger.info(f"{c}: {value:.2f}")
        """

        return value

    def get(self) -> list[le.ContourValue]:
        """Return the current RMS value mapped to all declared controls.

        :return: list of :class:`~loeric.core.element.ContourValue` events.
        """
        return [
            le.ContourValue(name=c, value=self._value, time=le.PerformanceClock.now())
            for c in self._controls
        ]


class BetterRMSConfig(AudioAnalyserConfig):
    """Config for :class:`BetterRMS`.

    :param controls: list of control names this analyser publishes values to.
    :param responsiveness: exponential smoothing factor in [0, 1].
    :param max_recovery: recovery rate of max value towards the current signal.
    :param min_recovery: recovery rate of min value towards the current signal.
    :param max_slack_factor: slack added to new maximum values
    (fraction of latest delta).
    :param min_slack_factor: slack added to new minimum values
    (fraction of latest delta).
    """

    controls: list[str]
    responsiveness: float
    max_recovery: float
    min_recovery: float
    max_slack_factor: float
    min_slack_factor: float


@lp.expose("_responsiveness", "responsiveness")
@lp.expose("_controls", "controls")
@lp.expose("_min_recovery", "min_recovery")
@lp.expose("_max_recovery", "max_recovery")
@lp.expose("_min_slack_factor", "min_slack_factor")
@lp.expose("_max_slack_factor", "max_slack_factor")
class BetterRMS(AudioAnalyser):
    """Root mean square analyser with exponential smoothing and dynamic normalisation.

    Tracks a smoothed RMS level and normalises it against a running min/max,
    producing a value in [0, 1]. The speed of adaptation is controlled by
    :attr:`responsiveness`.
    """

    config_class = BetterRMSConfig

    def __init__(
        self,
        responsiveness: float,
        controls: list[str],
        max_recovery: float,
        min_recovery: float,
        max_slack_factor: float,
        min_slack_factor: float,
        **kwargs,
    ):
        """Initialise the RMS analyser.

        :param responsiveness: exponential smoothing factor in [0, 1].
            Higher values track changes faster.
        :param controls: list of control names this analyser publishes values to.
        :param kwargs: forwarded to :class:`AudioAnalyser`.
        """
        super().__init__(**kwargs)

        self._responsiveness = responsiveness
        self._controls = controls
        self._max_slack_factor = max_slack_factor
        self._min_slack_factor = min_slack_factor
        self._max_recovery = max_recovery
        self._min_recovery = min_recovery
        self._level = None
        self._min_level = None
        self._max_level = None

    def _k_weighting(self, audio):
        """BS.1770-style K-weighting approximation.

        Stage 1:
            RLB high-pass (~38 Hz)

        Stage 2:
            high frequency emphasis

        This removes inaudible low-frequency energy and
        better approximates perceived loudness than raw energy.
        """
        hp = butter(
            2,
            38 / (self._samplerate / 2),
            btype="highpass",
            output="sos",
        )

        audio = sosfilt(
            hp,
            audio,
        )

        shelf = butter(
            2,
            1500 / (self._samplerate / 2),
            btype="highpass",
            output="sos",
        )

        audio = audio + 0.25 * sosfilt(
            shelf,
            audio,
        )

        return audio

    def _compute(self, buffer):
        """Compute the normalised RMS level from the accumulated buffer.

        Applies exponential smoothing to the level and running min/max,
        then normalises the result to [0, 1].

        :param buffer: audio window array of shape ``(channels, window_size)``.
        :return: normalised RMS value in [0, 1].
        """
        buffer = np.asarray(buffer, dtype=np.float32)

        # perceptual weighting
        buffer = self._k_weighting(buffer)

        loudness_value = np.mean(
            buffer * buffer,
            dtype=np.float64,
        )

        db = 10 * np.log10(max(loudness_value, 1e-12))
        if db < -45:
            return 0.5

        # smooth perceptual loudness
        if self._level is None:
            self._level = loudness_value
        else:
            self._level += self._responsiveness * (loudness_value - self._level)

        if self._min_level is None:
            self._min_level = self._level
            self._max_level = self._level

        else:
            # minimum envelope
            if self._level < self._min_level:
                jump = self._min_level - self._level
                self._min_level = self._level - jump * self._min_slack_factor
            else:
                self._min_level += self._min_recovery * (self._level - self._min_level)

            # maximum envelope
            if self._level > self._max_level:
                jump = self._level - self._max_level
                self._max_level = self._level + jump * self._max_slack_factor
            else:
                self._max_level += self._max_recovery * (self._level - self._max_level)

        value = np.clip(
            (self._level - self._min_level)
            / max(
                self._max_level - self._min_level,
                1e-9,
            ),
            0,
            1,
        )

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


class TempoAnalyserConfig(AudioAnalyserConfig):
    """Config for :class:`BetterRMS`.

    :param responsiveness: exponential smoothing factor in [0, 1].
    (fraction of latest delta).
    """

    responsiveness: float


@lp.expose("_controls", "controls")
@lp.expose("_responsiveness", "responsiveness")
class TempoAnalyser(AudioAnalyser):

    config_class = TempoAnalyserConfig

    def __init__(
        self,
        responsiveness: float,
        **kwargs,
    ):
        """Initialise the RMS analyser.

        :param responsiveness: exponential smoothing factor in [0, 1].
            Higher values track changes faster.
        :param controls: list of control names this analyser publishes values to.
        :param kwargs: forwarded to :class:`AudioAnalyser`.
        """
        super().__init__(**kwargs)

        self._responsiveness = responsiveness
        self._value = None

    def _k_weighting(self, audio):
        """BS.1770-style K-weighting approximation.

        Stage 1:
            RLB high-pass (~38 Hz)

        Stage 2:
            high frequency emphasis

        This removes inaudible low-frequency energy and
        better approximates perceived loudness than raw energy.
        """
        hp = butter(
            2,
            38 / (self._samplerate / 2),
            btype="highpass",
            output="sos",
        )

        audio = sosfilt(
            hp,
            audio,
        )

        shelf = butter(
            2,
            1500 / (self._samplerate / 2),
            btype="highpass",
            output="sos",
        )

        audio = audio + 0.25 * sosfilt(
            shelf,
            audio,
        )

        return audio

    def _compute(self, buffer):

        buffer = self._k_weighting(buffer)
        pitches, magnitudes = librosa.piptrack(y=buffer, sr=self._samplerate)

        # get indexes of the maximum value in each time slice
        max_indexes = np.argmax(magnitudes, axis=0)
        # get the pitches of the max indexes per time slice
        pitches = pitches[max_indexes, :]

        print(pitches)
        """
        hop_length = 512
        oenv = librosa.onset.onset_strength(
            y=buffer, sr=self._samplerate, hop_length=hop_length
        )
        tempogram = librosa.feature.tempogram(
            onset_envelope=oenv, sr=self._samplerate, hop_length=hop_length
        )
        # Compute global onset autocorrelation
        ac_global = librosa.autocorrelate(oenv, max_size=tempogram.shape[0])
        ac_global = librosa.util.normalize(ac_global)
        # Estimate the global tempo for display purposes
        chosen = librosa.feature.tempo(
            onset_envelope=oenv, sr=self._samplerate, hop_length=hop_length
        )[0][0]

        current = le.TempoKeeper.tempo().qpm

        tempo = current * (1 - self._responsiveness) + chosen * self._responsiveness

        logger.info(tempo)
        return tempo
        """
        return None

    def get(self) -> list[le.ContourValue]:
        """Return the current RMS value mapped to all declared controls.

        :return: list of :class:`~loeric.core.element.ContourValue` events.
        """
        if self._value is None:
            return []

        return [le.UserTempo(qpm=self._value, time=le.PerformanceClock.now())]
