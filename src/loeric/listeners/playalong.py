import argparse
import faulthandler
import threading
import time
import traceback

import mido
import numpy as np
import pyaudio


faulthandler.enable()
# bad code goes here


class PlayerThread:
    def __init__(self, invert):
        self.invert = invert
        self.stop = False

    def set_port(self, port_num):
        self.outport = port_num
        if self.outport is None:
            human_id = int(time.time())
            self.outport = mido.open_output(f"HUMAN out #{human_id}#", virtual=True)
        else:
            self.outport = mido.open_output(mido.get_output_names()[self.outport])

    def set_control(self, control_num):
        self.control_num = control_num

    def send_control(self, audio_monitor):
        try:
            self.old_value = -1

            self.send_control_loop(audio_monitor, self.callback)

        except Exception as e:
            traceback.print_exception(e)
            self.outport.panic()
            self.outport.close()

    def send_control_loop(self, audio_monitor, callback):
        while not self.stop:
            # get the audio level as percentage
            perc = audio_monitor.get()

            if self.invert:
                perc = 1 - perc

            callback(perc)

            time.sleep(1 / 10)

    def callback(self, perc):
        # adjust velocity
        value = int(perc * 127)
        value = max(0, value)
        value = min(127, value)

        if value != self.old_value:
            self.old_value = value

            msg = mido.Message(
                "control_change",
                channel=0,
                control=self.control_num,
                value=value,
            )

            # send the message
            self.outport.send(msg)
            print(f"{round(perc, 2)}\t{msg.value}")


class AudioMonitor:
    level = 0
    min_level = 10000000000
    max_level = 0

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
    stop = False

    def __init__(
        self, sample_rate, chunk_per_sec, device_index, num_channels, selected_channels
    ):
        self.RATE = sample_rate
        self.CHUNK = sample_rate // chunk_per_sec
        self.chunk_per_sec = chunk_per_sec
        self.device_index = device_index
        self.CHANNELS = num_channels
        self.selected_channels = selected_channels

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
            input_device_index=self.device_index,
        )

    def listen(self, audio_monitor, perc):
        # try:
        # listen while you can
        buffer = []
        while not self.stop:
            # get audio data
            data = self.stream.read(self.CHUNK)
            data = (
                np.frombuffer(data, np.int16)
                .reshape(-1, self.CHANNELS)
                .astype(np.int64)
            )
            data = data[self.selected_channels]

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
        "-l", "--list", help="list input audio devices and exit.", action="store_true"
    )
    parser.add_argument(
        "-d", "--device-index", help="the input audio device.", default=None, type=int
    )
    parser.add_argument(
        "-n",
        "--num-channels",
        help="the number of audio channels.",
        default=2,
        type=int,
    )
    parser.add_argument(
        "-s",
        "--selected-channels",
        help="the audio channels to consider.",
        nargs="+",
        type=int,
    )
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

    p = pyaudio.PyAudio()
    if args.list:
        numdevices = p.get_device_count()

        for i in range(0, numdevices):
            if (p.get_device_info_by_index(i).get("maxInputChannels")) > 0:
                print(
                    "Input Device id ",
                    i,
                    " - ",
                    p.get_device_info_by_index(i).get("name"),
                )
        return

    device_index = args.device_index
    if device_index is None:
        info = p.get_default_input_device_info()
        device_index = info["index"]

    info = p.get_device_info_by_index(device_index)
    name = info["name"]

    print(f"Connecting to device {device_index}: {name}")

    # create listening thread
    listener = ListenerThread(
        int(info["defaultSampleRate"]),
        args.chunks_per_second,
        device_index,
        args.num_channels,
        args.selected_channels,
    )
    listener.open_stream()

    # create audio monitor
    audio_monitor = AudioMonitor()

    # create playback thread
    player = PlayerThread(args.invert)
    player.set_port(args.output)
    player.set_control(args.control)

    # go until midi is playing
    t = threading.Thread(target=listener.listen, args=(audio_monitor, args.responsive))

    p = threading.Thread(target=player.send_control, args=[audio_monitor])

    try:
        t.start()
        p.start()

        while t.is_alive():
            t.join(1)

        while p.is_alive():
            p.join(1)

    except KeyboardInterrupt as e:
        print("Listener terminated by user.")
        traceback.print_exception(e)
        listener.stop = True
        player.stop = True
