import threading
import argparse
import mido
import pyaudio
import math
import time
import numpy as np


class PlayerThread:
    def __init__(self, port_num, control_num, invert):
        self.outport = mido.get_output_names()[port_num]
        self.control_num = control_num
        self.invert = invert

    def send_control(self, audio_monitor, listener):
        # get midi file
        with mido.open_output(self.outport) as port:
            # forever
            old_value = -1
            while True:
                # get the audio level as percentage
                perc = audio_monitor.get()

                if self.invert:
                    perc = 1 - perc

                # adjust velocity
                value = int(perc * 127)
                value = max(0, value)
                value = min(127, value)

                if value != old_value:
                    old_value = value

                    msg = mido.Message(
                        "control_change",
                        channel=0,
                        control=self.control_num,
                        value=value,
                    )

                    # send the message
                    port.send(msg)
                    print(f"{round(perc,2)}\t{msg.value}")

                    time.sleep(1 / 10)


class AudioMonitor:
    level = 0
    min_level = 10000000000
    max_level = 0
    it = 0

    lock = threading.RLock()

    def update(self, data, perc):
        # compute new level
        new_level = np.sqrt(np.mean(data**2))

        self.lock.acquire()

        # get the old level
        level = self.level

        # update
        level *= 1 - perc
        level += perc * new_level

        # update data

        self.level = level

        min_l = min(self.min_level, self.level)
        self.min_level *= 1 - perc
        self.min_level += perc * min_l

        max_l = max(self.max_level, self.level)
        self.max_level *= 1 - perc
        self.max_level += perc * max_l

        self.lock.release()

        # print(self.min_level, self.level, self.max_level)
        # print(self.get())

    # return percentage
    def get(self):
        self.lock.acquire()

        min_level = self.min_level
        max_level = self.max_level
        level = self.level

        self.lock.release()

        diff = max_level - min_level
        if diff == 0:
            value = 0
        else:
            value = (level - min_level) / (max_level - min_level)
        value = max(value, 0)
        value = min(value, 1)
        return value


class ListenerThread:
    FORMAT = pyaudio.paInt16
    CHANNELS = 2
    stop = False

    def __init__(self, sample_rate, chunk_per_sec):
        self.RATE = sample_rate
        self.CHUNK = sample_rate // chunk_per_sec
        self.chunk_per_sec = chunk_per_sec

    def open_stream(self):
        # open pyaudio instance
        self.p = pyaudio.PyAudio()

        # create a stream
        self.stream = self.p.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
        )

    def listen(self, audio_monitor, perc):
        # try:
        # listen while you can
        buffer = []
        while not self.stop:
            # get audio data
            data = self.stream.read(self.CHUNK)
            data = np.frombuffer(data, np.int16).astype(np.int64)

            buffer.append(data)

            if len(buffer) == self.chunk_per_sec:
                # send that to the monitor
                audio_monitor.update(np.concatenate(buffer), perc)
                buffer = buffer[1:]

        # close everything
        self.close_stream()

    def close_stream(self):
        # stop and close the stream
        self.stream.stop_stream()
        self.stream.close()

        # terminate pyaudio
        self.p.terminate()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o", "--output", help="the output MIDI port.", default=None, type=int
    )
    parser.add_argument(
        "-c",
        "--control",
        help="the control channel on which intensity is sent.",
        default=10,
        type=int,
    )
    parser.add_argument(
        "-cs",
        "--chunks-per-second",
        help="how many audio chunks will be considered to compute the control signal in one second.",
        default=10,
        type=int,
    )
    parser.add_argument(
        "-r",
        "--responsive",
        help="the weight of incoming values when computing intensity, in range 0 to 1.",
        default=1,
        type=float,
    )
    parser.add_argument(
        "--invert", action="store_true", help="whether to invert the signal or not"
    )
    args = parser.parse_args()

    # create listening thread
    listener = ListenerThread(48000, args.chunks_per_second)
    listener.open_stream()

    # create audio monitor
    audio_monitor = AudioMonitor()

    # create playback thread
    player = PlayerThread(args.output, args.control, args.invert)

    # go until midi is playing
    l = threading.Thread(target=listener.listen, args=(audio_monitor, args.responsive))

    p = threading.Thread(target=player.send_control, args=(audio_monitor, listener))

    l.start()
    # a = input()
    p.start()
