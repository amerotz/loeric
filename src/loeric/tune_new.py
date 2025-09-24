import mido
import argparse
import os
import numpy as np
import muspy as mp
import music21 as m21

import loeric_utils as lu

from collections.abc import Callable
from typing import Generator

# from . import loeric_utils as lu


class Tune:
    """A wrapper for a midi file."""

    def __init__(
        self,
        filename: str,
        repeats: int,
        key=None,
        meter=None,
        verbose: int = 0,
        sync_interval: float = None,
    ):
        """
        Initialize the class. A number of properties is computed:

        * the duration of the pickup bar, if there is any;
        * the key signature (only the first encountered is considered, key signature changes are not supported);
        * the time signature (only the first encountered is considered, time signature changes are not supported);

        :param filename: the path to the midi file.
        :param repeats: how many times the tune should be repeated.

        """
        self._verbose = verbose
        self._filename = filename

        if filename.endswith(".mid"):
            midi_source = mp.read_midi(filename)

        self._midi_source = midi_source.to_mido(use_note_off_message=True)
        self._tempo = self._get_original_tempo()
        self._8th_note_duration = 0.5 * 60 / self._tempo
        # 48ths
        self._measure_resolution = (60 / self._tempo) / 48

        note_pitches = np.array(
            [msg.note for msg in self._midi_source if lu.is_note_on(msg)]
        )[..., np.newaxis]
        note_times = np.round(
            np.diff(
                np.array(
                    [msg.time for msg in self._midi_source if lu.is_note(msg)]
                ).reshape(-1, 2),
                axis=1,
            )
            / self._measure_resolution,
        ) / np.round(self._8th_note_duration / self._measure_resolution)

        self._notes = np.concatenate((note_pitches, note_times), axis=1)
        print(self._notes)

        """
        # key signature
        self.forced_key = False
        if key is not None:
            root, mode = tuple(key.split(" "))
            key_signature = mp.KeySignature(time=0, root=lu.get_root(root), mode=mode)
            # reset key signatures
            mido_source.key_signatures = []
            self.forced_key = True
        else:
            key_signature = mido_source.key_signatures[0]

        self._key_signature = key_signature
        self._root = self._key_signature.root
        self._fifths = lu.number_of_fifths[
            (self._root + lu.mode_offset[self._key_signature.mode]) % 12
        ]
        """

        mido_source = mido_source.to_mido(use_note_off_message=True)

        """
        # fix timing so that every note on has time=0 and every note off has its duration
        notes = [msg for msg in mido_source]
        first = True
        for i in range(len(notes) - 1):

            if lu.is_note_off(notes[i]) and lu.is_note_on(notes[i + 1]):
                notes[i].time += notes[i + 1].time
                notes[i + 1].time = 0
        """

        # load midi notes and repeat them
        self._midi_source
        for i in range(repeats):
            # should find another way to handle repetitions
            self._orig_midi.append(mido.Message("sysex", data=[i], time=0))
            self._orig_midi.extend(list(notes))

        """
        # some stats about midi
        self._lowest_pitch = min(
            [msg.note for msg in self._orig_midi if msg.type in ["note_on", "note_off"]]
        )
        self._highest_pitch = max(
            [msg.note for msg in self._orig_midi if msg.type in ["note_on", "note_off"]]
        )

        # time signature
        self.forced_meter = False
        if meter is not None:
            self._time_signature = m21.meter.TimeSignature(meter)
            # reset key signatures
            mido_source.time_signatures = []
            self.forced_meter = True
        else:
            # time signature
            self._time_signature = self._get_time_signature()

        # tempo in microseconds per quarter
        self._tempo = self._get_original_tempo()

        # number of quarter notes per bar
        self._quarters_per_bar = (
            4 * self._time_signature.numerator / self._time_signature.denominator
        )
        # bar and beat duration in seconds
        self._bar_duration = self._quarters_per_bar * self._quarter_duration
        self._beat_duration = self._bar_duration / self._time_signature.beatCount

        # pickup bar
        self._offset = self._get_performance_offset()

        # to keep track of the performance
        self._performance_time = -self._offset

        # intertwine songpos messages every given interval
        # 16383 is the max value for songpos
        # every_n = max(6, round(len(self._midi) / 16383))
        self._sync_interval = sync_interval
        if self._sync_interval is None:
            every_duration = self._quarters_per_bar / self._time_signature.beatCount
        else:
            every_duration = self._sync_interval

        if self._verbose > 0:
            print(
                f"[INFO]\tSynchronizing every:\t{every_duration} quarters.",
            )

        # obtain alla events
        all_events = [m.copy() for m in self._orig_midi]

        # convert to cumulative time
        cumulative_time = 0
        for i, m in enumerate(all_events):
            cumulative_time += m.time
            all_events[i].time = cumulative_time

        # arange songpos messages independently
        songpos_timestamps = np.arange(
            start=0, stop=cumulative_time, step=every_duration
        )
        all_events.extend(
            [
                mido.Message("songpos", pos=p, time=t)
                for p, t in enumerate(songpos_timestamps)
            ]
        )

        # sort everything by cumulative time
        all_events = sorted(all_events, key=lambda x: x.time)

        # convert to time delta representation
        all_timestamps = [m.time for m in all_events]
        all_timestamps = np.diff(
            [m.time for m in all_events], prepend=all_timestamps[0]
        )
        for i in range(len(all_events)):
            all_events[i].time = float(all_timestamps[i])

        self.index_map = {}
        contour_index = 0
        cumulative_duration = 0
        self.duration_map = {}
        for i, msg in enumerate(all_events):

            cumulative_duration += msg.time

            if lu.is_note_on(msg):
                contour_index += 1
            elif msg.type == "songpos":
                # map songpos to next note and contour index
                self.index_map[msg.pos] = (i, contour_index)
                self.duration_map[msg.pos] = cumulative_duration - self._offset

        self._midi = all_events
        self._max_songpos = max(self.index_map.keys())

        if self._verbose > 0:
            print(f"[INFO]\tPlaying:\t\t{os.path.basename(filename)}")
            print(
                f"[INFO]\tMeter:\t\t\t{self._time_signature.numerator}/{self._time_signature.denominator}"
            )
            print(
                f"[INFO]\tKey:\t\t\t{self._key_signature.root} {self._key_signature.mode}"
            )


        """

    def _get_original_tempo(self) -> int:
        """
        Retrieve the tempo of the tune, if there is any.
        Only the first tempo change will be retrieved.

        :return: the first tempo change if there is any, else 120 bpm.
        """
        msg = self.filter(lambda x: x.type == "set_tempo")
        if len(msg) == 0:
            if self._verbose > 0:
                print("[INFO]\tSetting default tempo to 120 BPM")
            return 120
        if self._verbose > 0:
            print(f"[INFO]\tFile tempo is {mido.tempo2bpm(msg[0].tempo)} BPM")
        return mido.tempo2bpm(msg[0].tempo)

    def filter(
        self, filtering_function: Callable[[mido.Message], bool]
    ) -> list[mido.Message]:
        """
        Retrieve the midi events that fullfill the given filtering function.
        This function acts on the raw representation of the input tune without any songpos/meta/sysex messages, but with explicit repetitions.

        :param filtering_function: the function filtering the midi events.

        :return: a list of midi events fullfilling the filtering function.
        """
        return [msg for msg in self._midi_source if filtering_function(msg)]


parser = argparse.ArgumentParser()
parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
args = parser.parse_args()
args = vars(args)

tune = Tune(args["source"], 1, key=None, meter=None, verbose=False)
