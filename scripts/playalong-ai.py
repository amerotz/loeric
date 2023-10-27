import threading
import mido
import pyaudio
import math
import time
import numpy as np

from loeric.nebula.nebulaAI import NebulaAI


# global object and kickstart the AI
nebula = NebulaAI()

class PlayerThread:
    def __init__(self, port_num, control_num):
        self.outport = mido.get_output_names()[port_num]
        self.control_num = control_num

    def send_control(self):
        # get midi file
        with mido.open_output(self.outport) as port:
            # forever
            while True:
                # get the audio level as percentage
                # perc = audio_monitor.get()

                # get the output from the AI via the Hivemind Borg
                perc = nebula.hivemind.master_stream

                print(perc)

                # adjust velocity
                value = int(perc * 127)

                msg = mido.Message(
                    "control_change", channel=0, control=self.control_num, value=value
                )

                print(msg)
                # send the message
                port.send(msg)

                time.sleep(1 / 10)

#
# class AudioMonitor:
#     level = 0
#     min_levels = []
#     max_levels = []
#     min_level = 0
#     max_level = 0
#     it = 0
#
#     def update(self, data, perc):
#         # compute new level
#         data = data**2
#         new_level = np.sqrt(np.mean(data))
#
#         # get the old level
#         level = self.level
#
#         # update
#         level *= 1 - perc
#         level += perc * new_level
#
#         # update data
#         self.level = level
#
#         self.min_levels.append(np.sqrt(min(data)))
#         self.max_levels.append(np.sqrt(max(data)))
#
#         self.min_level = np.mean(self.min_levels)
#         self.max_level = np.mean(self.max_levels)
#
#         # print(self.min_level, self.level, self.max_level)
#         # print(self.get())
#
#     # return percentage
#     def get(self):
#         value = (self.level - self.min_level) / (
#             self.max_level - self.min_level + 0.0001
#         )
#         value = max(value, 0)
#         value = min(value, 1)
#         return value
#
#
# class ListenerThread:
#     CHUNK = 4096
#     FORMAT = pyaudio.paInt16
#     CHANNELS = 2
#     stop = False
#
#     def __init__(self, sample_rate):
#         self.RATE = sample_rate
#
#     def open_stream(self):
#         # open pyaudio instance
#         self.p = pyaudio.PyAudio()
#
#         # create a stream
#         self.stream = self.p.open(
#             format=self.FORMAT,
#             channels=self.CHANNELS,
#             rate=self.RATE,
#             input=True,
#             frames_per_buffer=self.CHUNK,
#         )
#
#     def listen(self, audio_monitor, perc):
#         # try:
#         # listen while you can
#         while not self.stop:
#             # get audio data
#             data = self.stream.read(self.CHUNK)
#
#             # get abs max amplitude
#             data = np.frombuffer(data, np.int16).astype(np.int64)
#
#             # send that to the monitor
#             audio_monitor.update(data, perc)
#
#         # close everything
#         self.close_stream()
#
#     def close_stream(self):
#         # stop and close the stream
#         self.stream.stop_stream()
#         self.stream.close()
#
#         # terminate pyaudio
#         self.p.terminate()


def main(args):
    # # create listening thread
    # listener = ListenerThread(48000)
    # listener.open_stream()

    # start NebulaAI
    # nebula = NebulaAI()
    nebula.thread_loop()

    # # create audio monitor
    # audio_monitor = AudioMonitor()

    # create playback thread
    player = PlayerThread(args.output, args.control)

    # go until midi is playing
    # l = threading.Thread(target=listener.listen, args=(audio_monitor, args.responsive))

    p = threading.Thread(target=player.send_control)

    # l.start()
    # a = input()
    p.start()


if __name__ == "__main__":
    import mido
    import argparse

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
        "-r",
        "--responsive",
        help="the weight of incoming values when computing intensity, in range 0 to 1.",
        default=1,
        type=float,
    )
    args = parser.parse_args()

    main(args)
