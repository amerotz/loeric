from threading import Thread

import numpy as np
import pyaudio
from mido import Message
from mido.ports import BaseOutput
from pyaudio import PyAudio

from loeric.listeners.playalong import AudioMonitor


class ListenerThread:
    FORMAT = pyaudio.paInt16
    stop = False
    invert = False
    stream = None
    num_channels = 1
    sample_rate = 48000
    chunk_per_sec = 10
    chunk = 4800
    perc = 1

    def __init__(self, device_index, control: BaseOutput, control_num: int):
        self.device_index = device_index
        self.control = control
        self.control_num = control_num
        self.audio_monitor = AudioMonitor()

    def start(self):
        thread = Thread(target=self.__listen)
        thread.start()

    def __listen(self):
        p = PyAudio()
        stream = p.open(
            format=self.FORMAT,
            channels=self.num_channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=self.device_index,
        )

        # listen while you can
        buffer = []
        old_value = 0
        while not self.stop:
            # get audio data
            data = stream.read(self.chunk)
            data = np.frombuffer(data, np.int16).astype(np.int64)

            buffer.append(data)

            if len(buffer) == self.chunk_per_sec:
                # send that to the monitor
                self.audio_monitor.update(np.concatenate(buffer), self.perc)
                buffer = buffer[1:]
                intensity = self.audio_monitor.get()

                if self.invert:
                    intensity = 1 - intensity

                # adjust velocity
                value = int(intensity * 127)
                value = max(0, value)
                value = min(127, value)
                if value != old_value:
                    old_value = value
                    print("Volume: ", value)
                    self.control.send(
                        Message(
                            "control_change",
                            channel=0,
                            control=self.control_num,
                            value=value,
                        )
                    )

        stream.stop_stream()
        stream.close()
        p.terminate()
