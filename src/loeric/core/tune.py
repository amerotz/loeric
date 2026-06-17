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

import copy
import logging
import os
from functools import cached_property

import muspy as mp
import numpy as np

import loeric.core.element as le

logger = logging.getLogger(__name__)


class Score:

    def __init__(self):
        self._annotated_score = []
        self._time_signatures = [None]
        self._key_signatures = [None]
        self._tempos = [None]

    @property
    def start_time(self) -> le.TimeDelta:
        """Return the start time of the score."""
        return self._annotated_score[0].time

    @property
    def end_time(self) -> le.TimeDelta:
        """Return the end time of the score."""
        return self._annotated_score[-1].time + self._annotated_score[-1].duration

    def ticks_to_eighth_notes(self, duration: int, ticks_per_quarter: int):
        return (
            2
            * np.round(le.MINIMUM_QUARTER_DIVISION * duration / ticks_per_quarter)
            / le.MINIMUM_QUARTER_DIVISION
        )

    @property
    def time_signatures(self):
        return self._time_signatures

    @property
    def key_signatures(self):
        return self._key_signatures

    @property
    def tempos(self):
        return self._tempos

    def _at(self, time: float | le.TimeDelta) -> list[le.LOERICElement]:
        """Return all events occurring at the specified time.

        Past the end of the score only EndOfScore will be returned.
        """
        if time > self.end_time:
            return [self._annotated_score[-1]]
        elif time < self.start_time:
            return []
        else:
            indexes = np.argwhere(
                self.all_float_times == time.eighth_duration
            ).flatten()
            return [self._annotated_score[i] for i in indexes]

    def _window(
        self, time: float | le.TimeDelta, size: float | le.TimeDelta
    ) -> list[le.LOERICElement]:
        """Return a window of tune elements from `time` to `time + size` (in eighth notes)."""
        if time >= self.end_time:
            return [self._annotated_score[-1]]
        elif size == 0:
            return []
        else:
            index_1 = np.argwhere(self.all_float_times >= float(time)).flatten()[0]
            index_2 = np.argwhere(self.all_float_times < float(time + size)).flatten()[
                -1
            ]
            window = []
            for i in range(index_1, index_2 + 1, 1):
                window.append(self._annotated_score[i])
            return window

    def at(self, time: float | le.TimeDelta) -> list[le.LOERICElement]:
        """Return all events occurring at the specified time.

        Past the end of the score only EndOfScore will be returned.
        """
        if time > self.end_time:
            return [self._annotated_score[-1]]
        elif time < self.start_time:
            return []
        else:
            t = time.eighth_duration if isinstance(time, le.TimeDelta) else float(time)
            times = self.all_float_times
            # binary search to the leftmost index that could match
            lo = int(np.searchsorted(times, t, side="left"))
            hi = int(np.searchsorted(times, t, side="right"))
            return [self._annotated_score[i] for i in range(lo, hi)]

    def window(
        self, time: float | le.TimeDelta, size: float | le.TimeDelta
    ) -> list[le.LOERICElement]:
        """Return a window of tune elements from `time` to `time + size` (in eighth notes)."""
        if time >= self.end_time:
            return [self._annotated_score[-1]]
        elif size == 0:
            return []
        else:
            t_start = float(time)
            t_end = float(time + size)
            times = self.all_float_times

            # searchsorted gives O(log N) bounds instead of two O(N) argwhere calls
            lo = int(np.searchsorted(times, t_start, side="left"))

            # exclusive upper bound
            hi = int(np.searchsorted(times, t_end, side="left"))

            # clamp to valid range
            if lo >= len(self._annotated_score):
                return []
            hi = min(hi, len(self._annotated_score))
            return self._annotated_score[lo:hi]

    @cached_property
    def pitches(self):
        return np.array(
            [
                note.pitch
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @cached_property
    def durations(self):
        return np.array(
            [
                note.duration
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @cached_property
    def float_durations(self):
        return np.array(
            [
                note.duration.eighth_duration
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @cached_property
    def all_float_times(self):
        return np.array([el.time.eighth_duration for el in self._annotated_score])

    @cached_property
    def times(self):
        return np.array(
            [
                note.time
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @cached_property
    def float_times(self):
        return np.array(
            [
                note.time.eighth_duration
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )


class NullTune(Score):
    """A tune containing only  null events."""

    def __init__(self):
        super().__init__()

    def at(time: float | le.TimeDelta):
        t = time
        if isinstance(time, le.TimeDelta):
            t = time.eighth_duration
        return le.NullEvent(time=t)


class Tune(Score):
    """A wrapper for a midi file."""

    def __init__(
        self,
        filename: str,
        repeats: int,
        sync_interval: float = None,
    ):
        """Initialize the class.

        :param filename: the path to the midi file.
        :param repeats: how many times the tune should be repeated.
        :param key: the key of the tune.
        :param meter: the meter of the tune.
        :param sync_interval: the synchronization interval for the virtual session.

        """
        super().__init__()

        self._sync_interval = None
        if sync_interval is not None:
            self._sync_interval = le.TimeDelta(eighth_duration=sync_interval)

        self._first_bar_length = 0

        if filename.endswith(".mid") or filename.endswith(".midi"):
            midi_source = mp.read_midi(filename)
        elif filename.endswith(".mxl"):
            midi_source = mp.read_musicxml(filename)
            self._first_bar_length = (
                midi_source.barlines[1].time - midi_source.barlines[0].time
            ) / 12

        elif filename.endswith(".abc"):
            midi_source = mp.read_abc(filename)
            self._first_bar_length = (
                midi_source.barlines[1].time - midi_source.barlines[0].time
            ) / 12

        else:
            raise Exception(
                f"Cannot read {filename}. Make sure it is a MIDI or ABC file."
            )

        ############################# tempo #############################

        self._tempos = [
            le.Tempo(
                qpm=t.qpm,
                time=self.ticks_to_eighth_notes(t.time, midi_source.resolution),
            )
            for t in midi_source.tempos
        ]

        ######################### key signature #########################

        # key signature
        self._key_signatures = []

        for key in midi_source.key_signatures:
            self._key_signatures.append(
                le.KeySignature(
                    root=key.root,
                    mode=key.mode,
                    time=self.ticks_to_eighth_notes(key.time, midi_source.resolution),
                )
            )

        self._current_key = self._key_signatures[0]

        ######################### time signature ########################

        # time signature
        self._time_signatures = []

        # time signature
        for sign in midi_source.time_signatures:
            self._time_signatures.append(
                le.TimeSignature(
                    numerator=sign.numerator,
                    denominator=sign.denominator,
                    time=self.ticks_to_eighth_notes(sign.time, midi_source.resolution),
                )
            )

        time_signature = self._time_signatures[0]
        if self._sync_interval is None:
            self._sync_interval = (
                time_signature.eighths_per_bar / time_signature.beat_count
            )

        self._first_bar_length %= time_signature.eighths_per_bar.eighth_duration
        logger.info(
            f"Synchronizing every:\t{self._sync_interval / 2} quarters.",
        )

        ######################### barlines ######################
        midi_source_barlines = []
        for i in range(len(midi_source.tracks)):
            midi_source_barlines.extend(midi_source.barlines)

        barline_times = np.array(
            [
                self.ticks_to_eighth_notes(msg.time, midi_source.resolution)
                for msg in midi_source_barlines
            ]
        )

        self._barlines = [
            le.Barline(number=i, time=t) for i, t in enumerate(barline_times)
        ]

        ######################### create the chords ######################

        midi_source_chords = []
        for i in range(len(midi_source.tracks)):
            midi_source_chords.extend(midi_source.tracks[i].chords)

        chord_pitches = [msg.pitches for msg in midi_source_chords]

        chord_times = np.array(
            [
                self.ticks_to_eighth_notes(msg.time, midi_source.resolution)
                for msg in midi_source_chords
            ]
        )

        self._original_chords = [
            le.Chord(pitches=p, time=t, is_user=True)
            for p, t in zip(chord_pitches, chord_times)
        ]

        ######################### create the notes ######################

        midi_source_notes = []
        for i in range(len(midi_source.tracks)):
            midi_source_notes.extend(midi_source.tracks[i].notes)

        # pitches
        note_pitches = np.array([msg.pitch for msg in midi_source_notes]).astype(float)

        # quantize durations
        note_durations = [
            self.ticks_to_eighth_notes(msg.duration, midi_source.resolution)
            for msg in midi_source_notes
        ]

        # id
        note_ids = np.arange(len(note_pitches))

        # time
        note_times = np.array(
            [
                self.ticks_to_eighth_notes(msg.time, midi_source.resolution)
                for msg in midi_source_notes
            ]
        )

        # pitch, duration, note id, time
        _score = [
            le.Note(pitch=p, eighth_duration=d, id=i, time=t)
            for p, d, i, t in zip(note_pitches, note_durations, note_ids, note_times)
        ]

        ######################### handle repetitions ######################

        # add repetitions
        score_duration = _score[-1].time + _score[-1].duration

        tmp_score = []
        repetitions = []
        chords = []
        key_signatures = []
        time_signatures = []
        tempos = []
        barlines = []

        # add notes and repetitions
        for r in range(repeats):
            new_score = copy.deepcopy(_score)
            for n in new_score:
                n.time += score_duration * r - self._first_bar_length
            repetitions.append(
                le.Repetition(number=r + 1, time=new_score[0].time.eighth_duration)
            )
            for k in self._key_signatures:
                key_signatures.append(
                    le.KeySignature(
                        root=k.root,
                        mode=k.mode,
                        time=(
                            k.time + score_duration * r - self._first_bar_length
                        ).eighth_duration,
                    )
                )
            for T in self._time_signatures:
                time_signatures.append(
                    le.TimeSignature(
                        numerator=T.numerator,
                        denominator=T.denominator,
                        time=(
                            T.time + score_duration * r - self._first_bar_length
                        ).eighth_duration,
                    )
                )
            for t in self._tempos:
                tempos.append(
                    le.Tempo(
                        qpm=t.qpm,
                        time=(
                            t.time + score_duration * r - self._first_bar_length
                        ).eighth_duration,
                    )
                )
            for b in self._barlines:
                barlines.append(
                    le.Barline(
                        number=b.number + r * len(self._barlines),
                        time=(
                            b.time + score_duration * r - self._first_bar_length
                        ).eighth_duration,
                    )
                )
            for c in self._original_chords:
                new_c = copy.deepcopy(c)
                new_c.time = c.time + score_duration * r - self._first_bar_length
                chords.append(new_c)
            tmp_score.extend(new_score)

        _score = tmp_score
        self._original_chords = chords
        self._key_signatures = key_signatures
        self._time_signatures = time_signatures
        self._tempos = tempos
        self._barlines = barlines

        _score = sorted(_score, key=lambda x: x.time)

        """
        # calculate end time for score with optional end trim
        _score_end_time = _score[-1].time + _score[-1].duration  # - trim_end_eighths

        # remove anything beyond end time (actually happens only if trimming)
        _score = [el for el in _score if el.time < _score_end_time]

        # recompute
        """
        _score_end_time = _score[-1].time + _score[-1].duration

        ############# score with repetition signs, songpos etc ###########

        self._annotated_score = []

        # add barlines
        self._annotated_score.extend(self._barlines)

        # add time signatures
        self._annotated_score.extend(self._time_signatures)

        # add key signatures
        self._annotated_score.extend(self._key_signatures)

        # add tempos
        self._annotated_score.extend(self._tempos)

        # add repetitions
        self._annotated_score.extend(repetitions)

        # add Chords
        self._annotated_score.extend(self._original_chords)

        # arange songpos messages independently
        self._position_times = np.arange(
            start=-self._first_bar_length,
            stop=_score_end_time.eighth_duration,
            step=self._sync_interval.eighth_duration,
        )
        song_positions = np.array(
            [
                le.SongPosition(position=p, time=t)
                for p, t in enumerate(self._position_times)
            ]
        )

        # divide add songpos in messages that contain a sync interval
        should_add_position = np.ones_like(song_positions).astype(bool)

        self._annotated_score.extend(song_positions[should_add_position])
        self._annotated_score.extend(_score)
        self._annotated_score.append(
            le.EndOfScore(time=_score_end_time.eighth_duration)
        )

        self._annotated_score.sort(key=lambda x: x.time)

        # add tune internal tag
        for e in self._annotated_score:
            e.add_tag("SCORE")

        # self.create_index_map()

        logger.info(f"Playing:\t{os.path.basename(filename)}")
        logger.info(
            f"Meter:\t{self._time_signatures[0].numerator}/{self._time_signatures[0].denominator}"
        )
        logger.info(
            f"Key:\t\t{self._key_signatures[0].root} {self._key_signatures[0].mode}"
        )
