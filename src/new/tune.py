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
import os

import element as le
import muspy as mp
import numpy as np


class Tune:
    """A wrapper for a midi file."""

    def __init__(
        self,
        filename: str,
        repeats: int,
        verbose: int = 0,
        sync_interval: float = None,
        config=None,
    ):
        """
        Initialize the class.

        :param filename: the path to the midi file.
        :param repeats: how many times the tune should be repeated.
        :param key: the key of the tune.
        :param meter: the meter of the tune.
        :param verbose: report info and errors.
        :param sync_interval: the synchronization interval for the virtual session.

        """

        self._verbose = verbose

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

        if self._sync_interval is None:
            time_signature = self._time_signatures[0]
            self._sync_interval = (
                time_signature.eighths_per_bar / time_signature.beat_count
            )

        self._first_bar_length %= self.time_signature.eighths_per_bar.eighth_duration
        if self._verbose > 0:
            print(
                f"[INFO]\tSynchronizing every:\t{self._sync_interval / 2} quarters.",
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

        # calculate end time for score with optional end trim
        self._score_end_time = (
            _score[-1].time + _score[-1].duration
        )  # - trim_end_eighths

        # remove anything beyond end time (actually happens only if trimming)
        _score = [el for el in _score if el.time < self._score_end_time]

        # recompute
        self._score_end_time = _score[-1].time + _score[-1].duration

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
            stop=self._score_end_time.eighth_duration,
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
            le.EndOfScore(time=self._score_end_time.eighth_duration)
        )

        self._annotated_score.sort(key=lambda x: x.time)

        # self.create_index_map()

        if self._verbose > 0:
            print(f"[INFO]\tPlaying:\t\t{os.path.basename(filename)}")
            print(
                f"[INFO]\tMeter:\t\t\t{self._time_signatures[0].numerator}/{self._time_signatures[0].denominator}"
            )
            print(
                f"[INFO]\tKey:\t\t\t{self._key_signatures[0].root} {self._key_signatures[0].mode}"
            )

    @property
    def start_time(self) -> le.TimeDelta:
        """Return the start time of the score."""
        return self._annotated_score[0].time

    @property
    def end_time(self) -> le.TimeDelta:
        """Return the end time of the score."""
        return self._score_end_time

    def ticks_to_eighth_notes(self, duration: int, ticks_per_quarter: int):
        return (
            2
            * np.round(le.MINIMUM_QUARTER_DIVISION * duration / ticks_per_quarter)
            / le.MINIMUM_QUARTER_DIVISION
        )

    @property
    def time_signature(self):
        return self._time_signatures[0]

    @property
    def key_signatures(self):
        return self._key_signatures

    def at(self, time: float | le.TimeDelta) -> list[le.LOERICElement]:
        """
        Return all events occurring at the specified time.
        Past the end of the score only EndOfScore will be returned.
        """
        if time > self._score_end_time:
            return [self._annotated_score[-1]]
        else:
            return [el for el in self._annotated_score if el.time == time]

    def window(
        self, time: float | le.TimeDelta, size: float | le.TimeDelta
    ) -> list[le.LOERICElement]:
        """
        Return a window of tune elements from `time` to `time + size` (in eighth notes).
        """

        if time > self._score_end_time:
            return [self._annotated_score[-1]]
        else:
            return [
                el
                for el in self._annotated_score
                if el.time >= time and el.time < time + size
            ]

    @property
    def pitches(self):
        return np.array(
            [
                note.pitch
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @property
    def durations(self):
        return np.array(
            [
                note.duration
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @property
    def float_durations(self):
        return np.array(
            [
                note.duration.eighth_duration
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @property
    def times(self):
        return np.array(
            [
                note.time
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )

    @property
    def float_times(self):
        return np.array(
            [
                note.time.eighth_duration
                for note in list(
                    filter(lambda x: isinstance(x, le.Note), self._annotated_score)
                )
            ]
        )
