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
import time
from collections import defaultdict

import mido
import numpy as np
import sounddevice as sd

import loeric.core.paths as lp

logger = logging.getLogger(__name__)


@lp.readonly("active")
@lp.readonly("type")
class InputInterface:
    """Abstract base for all input interfaces.

    Subclasses represent concrete input modalities (MIDI, audio, etc.) and
    expose a uniform :meth:`get` / :meth:`reset` interface to the player.
    """

    def __init__(self, name):
        """Initialise the input interface.

        :param name: identifier for this interface instance.
        """
        self._control_values = defaultdict(float)
        self._name = name
        self._type = "uninitialised"
        self._active = True

    @staticmethod
    def create_input(config: dict, name: str = None):
        """Instantiate the appropriate input interface from a config dict.

        :param config: interface configuration.
            Must contain ``active`` and ``type`` keys.
        :param name: identifier passed to the created interface.
        :return: a :class:`MIDIInput` or :class:`AudioInput` instance,
            or ``InputInterface`` (uninitialised) if ``active`` is false.
        :raises ValueError: if ``config["type"]`` is not recognised.
        """
        if not config["active"]:
            interface = InputInterface()
            interface._active = False
            interface._type = config["type"] + "(uninitialised)"
            return interface
        if config["type"] == "midi":
            return MIDIInput(
                name=name, port=config["port"], controls=config["controls"]
            )
        elif config["type"] == "audio":
            return AudioInput(
                name=name,
                device=config["device"],
                samplerate=config["samplerate"],
                analysers=config["analysers"],
            )
        else:
            raise ValueError(f"Unknown input interface type {config['type']}.")

    def reset(self):
        """Reset the interface state."""
        pass

    def get(self):
        """Return the current control values.

        :return: dict mapping control names to their current float values.
        """
        return self._control_values


@lp.expose("_controls", "controls")
@lp.readonly("port")
class MIDIInput(InputInterface):
    """Input interface for MIDI control change messages.

    Opens a MIDI port and maps incoming CC messages to named control values
    normalised to [0, 1].
    """

    _controls: dict[str, int]

    def __init__(self, name: str, port: str, controls: dict):
        """Open a MIDI input port and register the CC callback.

        :param name: identifier for this interface instance.
        :param port: name of the MIDI input port to open.
        :param controls: mapping of control names to MIDI CC numbers.
        """
        super().__init__(name)

        self._controls = controls
        self._type = "midi"
        self._midi_in = mido.open_input(port)
        self._midi_in.callback = self._callback()

    def _callback(self):
        """Build the MIDI message callback for the given control mapping.

        Filters non-CC messages. Normalises CC values to [0, 1].

        :param controls: mapping of control names to MIDI CC numbers.
        :return: callback function suitable for ``mido`` port assignment.
        """

        def f(message):
            if not message.is_cc:
                return
            for c in self._controls:
                if message.control == self._controls[c]:
                    self._control_values[c] = message.value / 127.0
                    logger.info(f"{c}: {self._control_values[c]}")

        return f

    def reset(self):
        """Close the MIDI input port."""
        self._midi_in.close()
        logger.info("Closed midi input.")


@lp.expose("_updates_per_second", "updates_per_second")
@lp.readonly("type")
class AudioInputFunction:
    """Base class for audio analysis functions operating on buffered audio frames.

    Accumulates audio data from a stream callback and triggers a compute step
    at a fixed rate. Subclasses implement :meth:`_compute` to produce a scalar
    control value from the buffer.
    """

    def __init__(self, type: str, updates_per_second: float):
        """Initialise the audio analysis function.

        :param type: identifier string for the function type.
        :param updates_per_second: how many times per second ``_compute`` is called.
        """
        self._type = type
        self._buffer = None
        self._value = 0
        self._last_update = 0
        self._updates_per_second = updates_per_second

    def update(self, indata):
        """Accumulate incoming audio data and trigger a compute step when due.

        :param indata: audio frame array from the sounddevice callback,
            shape ``(frames, channels)``.
        """
        if self._buffer is None:
            self._buffer = np.array(indata.T)
        else:
            self._buffer = np.concatenate((self._buffer, indata.T), axis=1)

        sleep_time = (1 / self._updates_per_second) - (time.time() - self._last_update)
        if sleep_time <= 0:
            self._last_update = time.time()
            self._buffer = np.squeeze(np.array(self._buffer))
            self._value = self._compute()
            self._buffer = None

    def reset(self):
        """Clear the internal audio buffer."""
        self._buffer = None

    def _compute(self):
        """Compute a value from the accumulated buffer.

        Override in subclasses to implement specific analysis logic.

        :return: computed float value. Base implementation always returns 0.
        """
        return 0

    def get(self):
        """Return the most recently computed value.

        :return: float value produced by the last ``_compute`` call.
        """
        return self._value

    @staticmethod
    def create_function(config: dict):
        """Instantiate the appropriate analysis function from a config dict.

        :param config: function configuration. Must contain a ``type`` key.
        :return: an :class:`AudioInputFunction` subclass instance.
        :raises ValueError: if ``config["type"]`` is not recognised.
        """
        if config["type"] == "rms":
            return RMS(
                **config,
            )
        else:
            raise ValueError(f"Unknown audio input function type {config['type']}.")


@lp.expose("_controls", "controls")
@lp.expose("_responsiveness", "responsiveness")
class RMS(AudioInputFunction):
    """Root mean square analyser with exponential smoothing and dynamic normalisation.

    Tracks a smoothed RMS level and normalises it against a running min/max,
    producing a value in [0, 1]. The speed of adaptation is controlled by
    :attr:`responsiveness`.
    """

    controls: list[str]

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
        :param kwargs: passed to :class:`AudioInputFunction`.
        """
        super().__init__(**kwargs)

        self._responsiveness = responsiveness
        self._controls = controls

        self._level = 0.0
        self._min_level = 10000000000.0
        self._max_level = 0.0

    def _compute(self):
        """Compute the normalised RMS level from the accumulated buffer.

        Applies exponential smoothing to the level and to the running min/max,
        then normalises the result to [0, 1].

        :return: normalised RMS value in [0, 1], or 0 if the buffer is empty.
        """
        if self._buffer is None:
            return 0

        # compute new level
        new_level = np.sqrt(np.mean(self._buffer**2))

        # get the old level
        level = self._level

        perc = self._responsiveness

        # update
        level *= 1 - perc
        level += perc * new_level

        # update data
        self._level = level

        min_l = min(self._min_level, self._level)
        self._min_level *= 1 - perc
        self._min_level += perc * min_l

        max_l = max(self._max_level, self._level)
        self._max_level *= 1 - perc
        self._max_level += perc * max_l

        diff = self._max_level - self._min_level
        if diff == 0:
            value = 0
        else:
            value = (level - self._min_level) / (self._max_level - self._min_level)
        value = max(value, 0)
        value = min(value, 1)

        # value = np.round(value, 2).astype(float)

        for c in self._controls:
            rv = str(np.round(value, 2))
            logger.info(f"{c}: {rv}")
        return value

    def get(self):
        """Return the current RMS value mapped to all declared controls.

        :return: dict mapping each control name to the current normalised RMS value.
        """
        return {c: self._value for c in self._controls}


# parts of this code taken from goofi-pipe audiostream node
@lp.readonly("samplerate")
@lp.readonly("device")
@lp.expose("_analysers", "analysers")
class AudioInput(InputInterface):
    """Input interface for live audio streams.

    Opens a sounddevice input stream and routes incoming frames to a set of
    :class:`AudioInputFunction` analysers. Exposes their outputs as named
    control values via :meth:`get`.
    """

    _analysers: dict[str, AudioInputFunction]

    @staticmethod
    def list_audio_devices():
        """List available audio input devices.

        :return: list of device name strings.
            Returns ``["None"]`` if sounddevice is unavailable.
        """
        if sd is None:
            return ["None"]

        devices = sd.query_devices()
        device_names = []
        for device in devices:
            # check if the device is an input device
            if device["max_input_channels"] > 0:
                device_names.append(device["name"])
        return device_names

    def __init__(self, name: str, device: str, samplerate: int, analysers: dict):
        """Open an audio input stream and initialise all configured analysers.

        :param name: identifier for this interface instance.
        :param device: sounddevice device name or index.
        :param samplerate: sampling rate in Hz.
        :param analysers: mapping of analyser names to their config dicts.
        """
        self._type = "audio"
        super().__init__(name)

        self._samplerate = samplerate
        self._device = device
        self._stream = sd.InputStream(
            callback=self._callback, samplerate=samplerate, device=device
        )

        self._analysers = {
            a: AudioInputFunction.create_function(analysers[a]) for a in analysers
        }

        self._stream.start()

    def _callback(self, indata, frames, time, status):
        """Sounddevice stream callback. Forwards incoming audio to all analysers.

        :param indata: audio frame array, shape ``(frames, channels)``.
        :param frames: number of frames in ``indata``.
        :param time: sounddevice timing info object.
        :param status: sounddevice stream status flags.
        """
        for a in self._analysers:
            self._analysers[a].update(indata)

    def get(self):
        """Return the merged control values from all active analysers.

        :return: dict mapping control names to their current float values.
        """
        val = {}
        for a in self._analysers:
            val |= self._analysers[a].get()
        return val

    def reset(self):
        """Stop and close the audio input stream."""
        # stop and close the stream
        self._stream.stop()
        self._stream.close()
        logger.info("Stopped and closed audio stream.")
