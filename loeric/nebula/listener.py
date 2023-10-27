import logging
import math
from random import random

# from sound.audio_data import LiveAudioData
from threading import Thread

import numpy as np
import pyaudio

#  import local methods
from loeric.nebula.hivemind import DataBorg


class Listener:
    def __init__(self):
        """
        controls audio listening by opening up a stream in Pyaudio.
        """
        print("starting listener")

        self.running = True
        self.connected = False
        self.logging = False

        # set up mic listening func
        self.CHUNK = 2**11
        self.RATE = 44100
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.RATE,
            input=True,
            frames_per_buffer=self.CHUNK,
        )

        # plug into the hive mind data borg
        self.hivemind = DataBorg()

        # todo - this is not currently important. Could get rid of FFT! [LOW]
        self.notes = [
            'A',
            'A#',
            'B',
            'C',
            'C#',
            'D',
            'D#',
            'E',
            'F',
            'F#',
            'G',
            'G#',
        ]

        # own the AI data server
        # self.engine = ai_engine

        t3 = Thread(target=self.snd_listen)
        t3.start()

    def snd_listen(self):
        """
        Listens to the microphone/ audio input. Logs the intensity/ amplitude
        to hivemind.
        A secondary function it analyses the input sound for a fundamental freq.
        This is currently a redundant function.
        """
        logging.info("mic listener: started!")
        while self.hivemind.running:
            data = np.frombuffer(
                self.stream.read(self.CHUNK, exception_on_overflow=False),
                dtype=np.int16,
            )
            peak = np.average(np.abs(data)) * 2
            if peak > 1000:
                bars = "#" * int(50 * peak / 2**16)
                print("MIC LISTENER: %05d %s" % (peak, bars))

                self.hivemind.mic_in = peak  # / 30000

                # normalise it for range 0.0 - 1.0
                normalised_peak = ((peak - 0) / (20000 - 0)) * (1 - 0) + 0
                if normalised_peak > 1.0:
                    normalised_peak = 1.0

                # put normalised amplitude into Nebula's dictionary for use
                self.hivemind.mic_in = normalised_peak

                # if loud sound then 63% affect gesture manager
                if normalised_peak > 0.8:
                    if random() > 0.36:
                        self.hivemind.interrupt_bang = False
                        self.hivemind.randomiser()
                        logging.info(
                            "-----------------------------INTERRUPT----------------------------"
                        )

    def freq_to_note(self, freq):
        # formula taken from https://en.wikipedia.org/wiki/Piano_key_frequencies
        note_number = 12 * math.log2(freq / 440) + 49
        note_number = round(note_number)

        note = (note_number - 1) % len(self.notes)
        note = self.notes[note]

        octave = (note_number + 8) // len(self.notes)

        return note, octave

    def terminate(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

if __name__ == "__main__":
    test = Listener()
    test.snd_listen()
