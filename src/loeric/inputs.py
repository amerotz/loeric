import logging
from collections import defaultdict
from numbers import Real

import mido
import numpy as np
import pyaudio

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
                frame_rate=config["frame_rate"],
                analysers=config["analysers"],
            )
        else:
            raise ValueError(f"Unknown input interface type {config["type"]}.")

    def reset(self):
        self._buffer = None

    def get(self):
        return self._control_values


class MIDIInput(InputInterface):

    def __init__(self, port: str, controls: dict, active: bool):

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

    def __init__(self, chunk_num: int):
        self._buffer = None
        self._chunks = []
        self._chunk_num = chunk_num

        self._value = 0

    def update(self, chunk):
        self._chunks.append(chunk)

        if len(self._chunks) == self._chunk_num:
            # send that to the monitor
            self._buffer = np.concatenate(self._chunks)
            self._chunks = self._chunks[1:]

            self._value = self._compute()

    def reset(self):
        self._buffer = None

    def _compute(self):
        return 0

    def get(self):
        return self._value

    @staticmethod
    def create_function(config: dict, samplerate: int, frame_rate: int):

        if config["type"] == "rms":
            return RMS(
                floor_mode=config["floor"],
                ceil_mode=config["ceil"],
                responsiveness=config["responsiveness"],
                controls=config["controls"],
                chunk_num=np.round(
                    (samplerate * config["window_size_seconds"]) / frame_rate
                ),
            )
        else:
            raise ValueError(f"Unknown audio input function type {config['type']}.")


class RMS(AudioInputFunction):

    def __init__(
        self,
        floor_mode: str | float,
        ceil_mode: str | float,
        responsiveness: float,
        controls: list,
        **kwargs,
    ):

        super().__init__(**kwargs)

        self._floor = floor_mode
        self._ceiling = ceil_mode

        self._old_value = None
        self._min_value = None
        self._max_value = None

        # convert from dbfs
        if isinstance(self._floor, Real):
            self._min_value = floor_mode

        if isinstance(self._ceiling, Real):
            self._max_value = ceil_mode

        self._responsiveness = responsiveness
        self._controls = controls

    def _compute(self):

        if self._buffer is None:
            return 0

        level = np.sqrt(np.mean(self._buffer**2))

        if self._old_value is not None:
            level = (
                self._responsiveness * level
                + (1 - self._responsiveness) * self._old_value
            )
        self._old_value = level

        level = 20 * np.log10(level + 1e-12)

        if self._floor == "adaptive":
            if self._min_value is None:
                self._min_value = level
            else:
                min_v = min(self._min_value, level)
                self._min_value *= 1 - self._responsiveness
                self._min_value += self._responsiveness * min_v

        if self._ceiling == "adaptive":
            if self._max_value is None:
                self._max_value = level
            else:
                max_v = max(self._max_value, level)
                self._max_value *= 1 - self._responsiveness
                self._max_value += self._responsiveness * max_v

        val = (level - self._min_value) / (self._max_value - self._min_value)
        val = min(max(0, val), 1)
        return val

    def get(self):
        return {c: self._value for c in self._controls}


class AudioInput(InputInterface):

    @staticmethod
    def list_devices():
        _P = pyaudio.PyAudio()

        numdevices = _P.get_device_count()
        for i in range(0, numdevices):
            if (_P.get_device_info_by_index(i).get("maxInputChannels")) > 0:
                print(
                    "Input Device id ",
                    i,
                    " - ",
                    _P.get_device_info_by_index(i).get("name"),
                )

        _P.terminate()

    def __init__(self, device: str, frame_rate: int, analysers: dict):

        super().__init__()

        self._P = pyaudio.PyAudio()
        self._frame_rate = frame_rate
        self._stream, self._samplerate, self._channels = self._open_stream_by_name(
            device
        )

        self._functions = [
            AudioInputFunction.create_function(
                analysers[a], self._samplerate, self._frame_rate
            )
            for a in analysers
        ]

        self._stream.start_stream()

    def _callback(self):

        def f(in_data, frame_count, time_info, status):

            chunk = np.frombuffer(in_data, dtype=np.float32).reshape(-1, self._channels)

            for f in self._functions:
                f.update(chunk)

            # return silence float32 mono silence
            # though pyaudio with output=false will ignore
            out = b"\x00" * frame_count * 4
            return (out, pyaudio.paContinue)

        return f

    def _open_stream_by_name(self, name: str):

        device_index = None
        device_info = None

        # find device by substring match
        for i in range(self._P.get_device_count()):
            info = self._P.get_device_info_by_index(i)
            if name.lower() in info["name"].lower():
                device_index = i
                device_info = info
                logger.info(
                    f"Found request audio device '{name}' at index {device_index}."
                )
                break

        if device_index is None:
            raise ValueError(f"Device '{name}' not found")

        # pick defaults safely
        rate = int(device_info.get("defaultSampleRate", 44100))
        channels = int(device_info.get("maxInputChannels"))

        stream = self._P.open(
            format=pyaudio.paFloat32,
            channels=max(1, channels),
            rate=rate,
            input=True,
            output=False,
            input_device_index=device_index,
            output_device_index=None,
            frames_per_buffer=self._frame_rate,
            stream_callback=self._callback(),
        )
        logger.info(f"Opeed input stream '{name}'.")

        return stream, rate, channels

    def get(self):
        val = {}
        for f in self._functions:
            val |= f.get()
        return val

    def reset(self):
        # stop and close the stream
        self._stream.stop_stream()
        self._stream.close()
        logger.info("Stopped and closed audio stream.")

        # terminate pyaudio
        self._P.terminate()
