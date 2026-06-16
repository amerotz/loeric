import logging
import time
from collections import defaultdict

import mido
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class InputInterface:

    def __init__(self):
        self._control_values = defaultdict(float)

    @staticmethod
    def create_input(config: dict):

        if not config["active"]:
            return None
        if config["type"] == "midi":
            return MIDIInput(port=config["port"], controls=config["controls"])
        elif config["type"] == "audio":
            return AudioInput(
                device=config["device"],
                samplerate=config["samplerate"],
                analysers=config["analysers"],
            )
        else:
            raise ValueError(f"Unknown input interface type {config["type"]}.")

    def reset(self):
        self._buffer = None

    def get(self):
        return self._control_values


class MIDIInput(InputInterface):

    def __init__(self, port: str, controls: dict):

        super().__init__()

        self._midi_in = mido.open_input(port)
        self._midi_in.callback = self._callback(controls)

    def _callback(self, controls):

        def f(message):
            if not message.is_cc:
                return
            for c in controls:
                if message.control == controls[c]:
                    self._control_values[c] = message.value / 127.0
                    logger.info(f"{c}: {self._control_values[c]}")

        return f

    def reset(self):
        self._midi_in.close()
        logger.info("Closed midi input.")


class AudioInputFunction:

    def __init__(self, type: str, updates_per_second: float):
        self._type = type
        self._buffer = None
        self._value = 0
        self._last_update = 0
        self._seconds_per_update = 1 / updates_per_second

    def update(self, indata):
        if self._buffer is None:
            self._buffer = np.array(indata.T)
        else:
            self._buffer = np.concatenate((self._buffer, indata.T), axis=1)

        sleep_time = self._seconds_per_update - (time.time() - self._last_update)
        if sleep_time <= 0:
            self._last_update = time.time()
            self._buffer = np.squeeze(np.array(self._buffer))
            self._value = self._compute()
            self._buffer = None

    def reset(self):
        self._buffer = None

    def _compute(self):
        return 0

    def get(self):
        return self._value

    @staticmethod
    def create_function(config: dict):

        if config["type"] == "rms":
            return RMS(
                **config,
            )
        else:
            raise ValueError(f"Unknown audio input function type {config['type']}.")


class RMS(AudioInputFunction):

    def __init__(
        self,
        responsiveness: float,
        controls: list,
        **kwargs,
    ):

        super().__init__(**kwargs)

        self._responsiveness = responsiveness
        self._controls = controls

        self._level = 0.0
        self._min_level = 10000000000.0
        self._max_level = 0.0

    def _compute(self):

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
        return {c: self._value for c in self._controls}


# parts of this code taken from goofi-pipe audiostream node
class AudioInput(InputInterface):

    @staticmethod
    def list_audio_devices():
        """Returns a list of available audio devices."""
        if sd is None:
            return ["None"]

        devices = sd.query_devices()
        device_names = []
        for device in devices:
            # check if the device is an input device
            if device["max_input_channels"] > 0:
                device_names.append(device["name"])
        return device_names

    def __init__(self, device: str, samplerate: int, analysers: dict):

        super().__init__()

        self._stream = sd.InputStream(
            callback=self._callback, samplerate=samplerate, device=device
        )

        self._functions = [
            AudioInputFunction.create_function(analysers[a]) for a in analysers
        ]

        self._stream.start()

    def _callback(self, indata, frames, time, status):

        for f in self._functions:
            f.update(indata)

    def get(self):
        val = {}
        for f in self._functions:
            val |= f.get()
        return val

    def reset(self):
        # stop and close the stream
        self._stream.stop()
        self._stream.close()
        logger.info("Stopped and closed audio stream.")
