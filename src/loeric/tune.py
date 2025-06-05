import mido
import numpy as np
import muspy as mp
import music21 as m21

from collections.abc import Callable
from typing import Generator

from . import loeric_utils as lu


class Tune:
    """A wrapper for a midi file."""

    def __init__(self, filename: str, repeats: int, key=None):
        """
        Initialize the class. A number of properties is computed:

        * the duration of the pickup bar, if there is any;
        * the key signature (only the first encountered is considered, key signature changes are not supported);
        * the time signature (only the first encountered is considered, time signature changes are not supported);

        :param filename: the path to the midi file.
        :param repeats: how many times the tune should be repeated.

        """
        self._filename = filename
        if filename.endswith(".mid"):
            mido_source = mp.read_midi(filename)
        elif filename.endswith(".abc"):
            mido_source = mp.read_abc(filename)

        # key signature
        if key is not None:
            root, mode = tuple(key.split(" "))
            self._key_signature = mp.KeySignature(
                time=0, root=lu.get_root(root), mode=mode
            )
        else:
            self._key_signature = mido_source.key_signatures[0]
        print(self._key_signature)

        self._root = self._key_signature.root
        self._fifths = lu.number_of_fifths[
            (self._root + lu.mode_offset[self._key_signature.mode]) % 12
        ]
        mido_source = mido_source.to_mido(use_note_off_message=True)

        # load midi notes and repeat them
        self._orig_midi = []
        for i in range(repeats):
            # should find another way to handle repetitions
            self._orig_midi.append(mido.Message("sysex", data=[i]))
            self._orig_midi.extend(list(mido_source))

        # some stats about midi
        self._lowest_pitch = min(
            [msg.note for msg in self._orig_midi if msg.type in ["note_on", "note_off"]]
        )
        self._highest_pitch = max(
            [msg.note for msg in self._orig_midi if msg.type in ["note_on", "note_off"]]
        )

        # time signature
        self._time_signature = self._get_time_signature()

        # tempo in microseconds per quarter
        self._tempo = self._get_original_tempo()

        # number of quarter notes per bar
        quarters_per_bar = (
            4 * self._time_signature.numerator / self._time_signature.denominator
        )
        # bar and beat duration in seconds
        self._bar_duration = quarters_per_bar * self._quarter_duration
        self._beat_duration = self._bar_duration / self._time_signature.beatCount

        # pickup bar
        self._offset = self._get_performance_offset()

        # to keep track of the performance
        self._performance_time = -self._offset

        # intertwine songpos messages every given interval
        # 16383 is the max value for songpos
        # every_n = max(6, round(len(self._midi) / 16383))
        every_duration = self._beat_duration
        print("Sync every", quarters_per_bar / self._time_signature.beatCount)

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

        print(f"Playing:\t{filename}")
        print(f"Meter:\t{self._time_signature}")
        print(f"Key:\t{self._key_signature}")

    @property
    def beat_count(self) -> int:
        """
        :return: the numebr of beats in the tune.
        """
        return self._time_signature.beatCount

    @property
    def quarter_duration(self) -> float:
        """
        :return: the duration of a quarter note in the tune given its original tempo.
        """
        return self._quarter_duration

    @property
    def root(self) -> int:
        """
        :return: the tune's key signature root in pitch space.
        """
        return self._root

    @property
    def major_root(self) -> int:
        """
        :return: the root of the relative major of the tune's key signature in pitch space.
        """
        return (self._root + lu.mode_offset[self._key_signature.mode]) % 12

    @property
    def ambitus(self) -> tuple[int]:
        """
        :return: the tune's lowest and highest pitches in a tuple (low, high)
        """
        return (self._lowest_pitch, self._highest_pitch)

    @property
    def key_signature(self) -> str:
        """
        :return: the tune's key signature.
        """
        return self._key_signature

    @property
    def time_signature(self) -> m21.meter.TimeSignature:
        """
        :return: the tune's time signature.
        """
        return self._time_signature

    @property
    def tempo(self) -> int:
        """
        :return: the tune's tempo in microseconds per quarter.
        """
        return self._tempo

    @property
    def bar_duration(self) -> float:
        """
        :return: the tune's bar duration in seconds.
        """
        return self._bar_duration

    @property
    def beat_duration(self) -> float:
        """
        :return: the tune's beat duration in seconds.
        """
        return self._beat_duration

    @property
    def offset(self) -> float:
        """
        :return: the tune's performance offset (i.e. the length of the pickup bar) in seconds.
        """
        return self._offset

    def reset_performance_time(self) -> None:
        """
        :return: the current performance time
        """
        self._performance_time = -self._offset

    def get_performance_time(self) -> float:
        """
        :return: the current performance time
        """
        return self._performance_time

    @property
    def _quarter_duration(self) -> float:
        """
        Return the duration of a quarter note in seconds given the current tempo.

        :return: the amount of seconds corresponding to a quarter note given the current tempo.
        """
        return self._tempo / 1e6

    def semitones_from_tonic(self, midi_note: int) -> int:
        """
        Compute the distance between the given note and the tonic of the tune in semitones.

        :param midi_note: the input note.

        :return: the distance between note and the tonic in semitones.
        """
        return (midi_note - 7 * self._fifths) % 12

    def _get_performance_offset(self) -> float:
        """
        Return the length of the pickup bar, if there is any.

        :return: the length of the pickup bar in seconds.
        """
        # retrieve duration of first bar
        m21_source = m21.converter.parse(self._filename)

        # performance offset in quarter length
        offset = list(m21_source.recurse().getElementsByClass("Measure"))[
            0
        ].duration.quarterLength

        # convert quarter length to seconds
        offset *= self._quarter_duration
        offset %= self._bar_duration

        return offset

    def _get_original_tempo(self) -> int:
        """
        Retrieve the tempo of the tune, if there is any.
        Only the first tempo change will be retrieved.

        :return: the first tempo change if there is any, else 120 bpm.
        """
        msg = self.filter(lambda x: x.type == "set_tempo")
        if len(msg) == 0:
            return mido.bpm2tempo(120)
        return msg[0].tempo

    def _get_time_signature(self) -> m21.meter.TimeSignature:
        """
        Retrieve the time signature of the tune, if there is any.
        Only the first time signature will be retrieved.

        :return: the first time signature if there is any, else None.
        """

        # msg = [m for m in self._midi if m.type == "time_signature"][0]
        msg = self.filter(lambda x: x.type == "time_signature")
        if len(msg) == 0:
            return None
        time_signature = m21.meter.TimeSignature()
        time_signature.numerator = msg[0].numerator
        time_signature.denominator = msg[0].denominator
        return time_signature

    def _get_key_signature(self) -> str:
        """
        Retrieve the key signature of the tune, if there is any.
        Only the first key signature will be retrieved.

        :return: the first key signature if there is any, else None.
        """

        # msg = [m for m in self._midi if m.type == "key_signature"]
        msg = self.filter(lambda x: x.type == "key_signature")
        if len(msg) == 0:
            return None
        return msg[0].key

    def filter(
        self, filtering_function: Callable[[mido.Message], bool]
    ) -> list[mido.Message]:
        """
        Retrieve the midi events that fullfill the given filtering function.
        This function acts on the raw representation of the input tune without any songpos/meta/sysex messages, but with explicit repetitions.

        :param filtering_function: the function filtering the midi events.

        :return: a list of midi events fullfilling the filtering function.
        """
        return [msg for msg in self._orig_midi if filtering_function(msg)]

    def events(self) -> Generator[mido.Message, None, None]:
        """
        A generator returning each midi event in the tune. Each time an event is retrieved, the performance time is updated.

        :return: the sequence of midi events one by one
        """
        # for each note
        for event in self._midi:
            # update the performance time
            self._performance_time += event.time

            # return the event
            yield event

    def is_on_a_beat(self) -> bool:
        """
        Decide if we are on a beat or not, given the current cumulative performance time.

        :return: True if we are on a beat.
        """
        beat_position = (
            self._performance_time % self._bar_duration
        ) / self._beat_duration
        diff = abs(beat_position - round(beat_position))

        return diff <= lu.TRIGGER_DELTA

    def __len__(self) -> int:
        """
        Return the length of the list of midi messages.

        :return: the number of midi messages in this tune.
        """
        return len(self._midi)

    def __getitem__(self, idx: int) -> mido.Message:
        """
        Return the item in the midi event list corresponding to the given index.

        :param idx: the element index.

        :return: the midi message corresponding to that index.
        """
        return self._midi[idx]
