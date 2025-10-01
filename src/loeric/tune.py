import argparse
import random
import os
import numpy as np
import muspy as mp
import mido

from . import loeric_utils as lu

############################# CONSTANTS #########################

MINIMUM_QUARTER_DIVISION = 48


def quantize(eighth_duration):
    return np.round(eighth_duration * MINIMUM_QUARTER_DIVISION / 2) / (
        MINIMUM_QUARTER_DIVISION / 2
    )


def note_list_to_midi(notes):

    midi_messages = []
    for note in notes:
        midi_messages.extend(note.to_midi(absolute_time=True))

    # sort by time
    midi_messages.sort(key=lambda x: x.time)

    """
    # relative time
    new_times = np.array([m.time for m in midi_messages])
    new_times = np.insert(np.diff(new_times), 0, 0)

    # reassign timings
    for i in range(len(midi_messages)):
        midi_messages[i].time = new_times[i]
    """

    return midi_messages


class ScoreElement:

    def __init__(self, time: float = 0):
        self._time = time
        self._is_note = False
        self._eighth_duration = 0
        self._absolute_duration = 0

    @property
    def time(self):
        return self._time

    @property
    def is_note(self):
        return self._is_note

    @property
    def eighth_duration(self):
        return self._eighth_duration

    @property
    def absolute_duration(self):
        return self._absolute_duration

    @eighth_duration.setter
    def eighth_duration(self, value):
        self._eighth_duration = value


class Pause(ScoreElement):

    def __init__(self, eighth_duration, time: float = 0):
        super().__init__(time)

        self._eight_duration = eighth_duration

    @property
    def pitch(self):
        return -1

    def __repr__(self):
        return f"(Pause d={np.round(self._eighth_duration,4)} t={self._time})"

    def to_midi(self, absolute_time=False):
        time = self._eight_duration
        if absolute_time:
            time += self._time

        return [mido.Message("note_off", note=0, time=time)]


class SongPosition(ScoreElement):

    def __init__(self, position: int = 0, time: float = 0):
        super().__init__(time)

        self._position = position

    @property
    def position(self):
        return self._position

    def __repr__(self):
        return f"(Position p={self._position} t={self._time})"

    def to_midi(self):
        return mido.Message("songpos", pos=self._position, time=self._time)


class Tempo(ScoreElement):

    def __init__(self, qpm: float = 0, time: float = 0):
        super().__init__(time)

        self._qpm = qpm

    @property
    def qpm(self):
        return self._qpm

    def __repr__(self):
        return f"(Tempo q={self._qpm} t={self._time})"


class KeySignature(ScoreElement):

    def __init__(self, root: int = 0, mode: str = "major", time: float = 0):
        super().__init__(time)

        self._root = root
        self._mode = mode
        self._fifths = lu.number_of_fifths[self.major_root]

    @property
    def root(self):
        return self._root

    @property
    def mode(self):
        return self._mode

    @property
    def fifths(self):
        return self._fifths

    def semitones_from_root(self, pitch: int) -> int:
        """
        Compute the distance between the given note and the tonic of the tune in semitones.

        :param pitch: the input note.

        :return: the distance between note and the tonic in semitones.
        """
        return int((pitch - 7 * self._fifths) % 12)

    def __repr__(self):
        return f"(KeySignature k={self._root} m={self._mode} t={self._time})"

    def to_midi(self):
        names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        return mido.MetaMessage(
            "key_signature", key=names[self.major_root], time=self._time
        )

    @property
    def major_root(self) -> int:
        mode_offset = {
            "major": 0,
            "minor": 3,
            "dorian": 10,
            "mixolydian": 5,
        }
        return (self._root + mode_offset[self._mode]) % 12


class TimeSignature(ScoreElement):

    def __init__(self, numerator: int, denominator: int, time: float):
        super().__init__(time)

        self._numerator = numerator
        self._denominator = denominator
        self._quarters_per_bar = 4 * numerator / denominator

        if self._numerator % 3 == 0:
            self._beat_count = self._numerator / 3
        else:
            self._beat_count = self._numerator

    @property
    def numerator(self):
        return self._numerator

    @property
    def denominator(self):
        return self._denominator

    @property
    def quarters_per_bar(self):
        return self._quarters_per_bar

    @property
    def beat_count(self):
        return self._beat_count

    def __repr__(self):
        return f"(TimeSignature {self._numerator}/{self._denominator} t={self._time})"


class Repetition(ScoreElement):

    def __init__(self, number: int = 0, time: float = 0):
        super().__init__(time)

        self._number = number

    @property
    def number(self):
        return self._number

    def __repr__(self):
        return f"(Repetition n={self._number} t={np.round(self._time, 4)})"


class NoteGroup(ScoreElement):

    def __init__(self, time=0):
        super().__init__(time)

        self._notes = []
        self._absolute_duration = 0
        self._time = None

    def add(self, note):
        self._notes.append(note)
        if self._time is None:
            self._time = note.time
            self._absolute_duration = note.absolute_duration
        else:
            if self._absolute_duration != 0:
                self._absolute_duration = absolute_add(
                    self._absolute_duration, note.absolute_duration
                )
                self._eighth_duration = 8 / self._absolute_duration
        self._is_note = self._is_note or note.is_note

    def __repr__(self):
        s = f"(NoteGroup d={np.round(self._eighth_duration, 4)} t={self._time})"
        for note in self._notes:
            s += "\n\t" + str(note)
        return s


class Note(ScoreElement):

    def __init__(
        self,
        pitch: float = 0,
        eighth_duration: float = 1,
        id: int = 0,
        time: float = 0,
        velocity=64,
        slide=False,
        channel=0,
    ):
        super().__init__(time)
        self._pitch = pitch
        self._eighth_duration = quantize(eighth_duration)
        if eighth_duration != 0:
            self._absolute_duration = 8 / eighth_duration
        self._id = id
        self._is_note = True
        self._velocity = velocity
        self._is_slide = slide
        self._slide_targets = []
        self.channel = channel

    def __repr__(self):
        return f"(Note p={self._pitch} d={np.round(self._eighth_duration,4)} id={self._id} t={np.round(self._time,4)})"

    def transpose(self, semitones):
        self._pitch += semitones
        if self._is_slide:
            for note in self._slide_targets:
                note.transpose(semitones)

    def add_slide_target_pitch(self, note):
        if not self._is_slide:
            raise Exception(
                "slide not permitted. This note was created with slide=True."
            )
        self._slide_targets.append(note)
        # print(self._pitch, self._slide_targets, self._eighth_duration)
        duration = self._slide_targets[0].absolute_duration
        for note in self._slide_targets[1:]:
            duration = absolute_add(duration, note.absolute_duration)
        """
        assert (
            duration >= self._absolute_duration
        ), f"Duration of targets {duration} exceeds note duration {self._absolute_duration}"
        """

    @property
    def eighth_duration(self):
        return self._eighth_duration

    @eighth_duration.setter
    def eighth_duration(self, value):
        self._eighth_duration = quantize(value)
        if value != 0:
            self._absolute_duration = 8 / value

    @property
    def pitch(self):
        return self._pitch

    @property
    def id(self):
        return self._id

    def to_midi(self, absolute_time=False):

        overall_time = 0
        if absolute_time:
            overall_time = self._time

        messages = []
        messages.append(
            mido.Message(
                "pitchwheel",
                pitch=np.round(8192 * (np.round(self._pitch) - self._pitch)).astype(
                    int
                ),
                channel=self.channel,
                time=overall_time,
            )
        )
        messages.append(
            mido.Message(
                "note_on",
                note=np.round(self._pitch).astype(int),
                time=overall_time,
                channel=self.channel,
                velocity=self._velocity,
            )
        )

        note_duration = self._eighth_duration
        if self._is_slide:

            previous_bend = 0
            resolution = 24

            for note in self._slide_targets:
                slide_duration = note.eighth_duration / resolution

                bend = max(
                    min(4096.0 * (note.pitch - self._pitch), 8191),
                    -8192,
                )
                # print(previous_bend, bend)

                # append messages
                mult = random.uniform(0.25, 0.5)
                for j in range(resolution):
                    if absolute_time:
                        overall_time += slide_duration
                    perc = j / resolution
                    perc **= mult
                    pb = (1 - perc) * previous_bend + perc * bend
                    pb = int(pb)
                    messages.append(
                        mido.Message(
                            "pitchwheel",
                            pitch=pb,
                            channel=self.channel,
                            time=overall_time,
                        )
                    )
                    note_duration -= slide_duration

                previous_bend = bend

        messages.append(
            mido.Message(
                "note_off",
                note=np.round(self._pitch).astype(int),
                channel=self.channel,
                time=overall_time + note_duration,
                velocity=0,
            )
        )
        return messages


def absolute_add(a: float, b: float) -> float:
    return (a * b) / (a + b)


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
        Initialize the class.

        :param filename: the path to the midi file.
        :param repeats: how many times the tune should be repeated.
        :param key: the key of the tune.
        :param meter: the meter of the tune.
        :param verbose: report info and errors.
        :param sync_interval: the synchronization interval for the virtual session.

        """
        self._filename = filename
        self._verbose = verbose
        self._sync_interval = sync_interval

        if filename.endswith(".mid") or filename.endswith(".midi"):
            midi_source = mp.read_midi(filename)
        else:
            raise Exception("Cannot read this file. Make sure it is a midi file.")

        ############################# tempo #############################

        self._tempos = [
            Tempo(
                qpm=t.qpm,
                time=self.ticks_to_eighth_notes(t.time, midi_source.resolution),
            )
            for t in midi_source.tempos
        ]

        ######################### key signature #########################

        # key signature
        self.forced_key = False
        self._key_signatures = []
        if key is not None:

            root, mode = tuple(key.split(" "))

            self._key_signatures.append(
                KeySignature(root=lu.get_root(root), mode=mode, time=0)
            )

            self.forced_key = True
        else:
            for key in midi_source.key_signatures:
                self._key_signatures.append(
                    KeySignature(
                        root=key.root,
                        mode=key.mode,
                        time=self.ticks_to_eighth_notes(
                            key.time, midi_source.resolution
                        ),
                    )
                )

        self._current_key = self._key_signatures[0]

        ######################### time signature ########################

        # time signature
        self.forced_meter = False
        self._time_signatures = []
        if meter is not None:
            num, den = meter.split("/")
            self._time_signatures.append(
                TimeSignature(numerator=int(num), denominator=int(den), time=0)
            )
            self.forced_meter = True
        else:
            # time signature
            for sign in midi_source.time_signatures:
                self._time_signatures.append(
                    TimeSignature(
                        numerator=sign.numerator,
                        denominator=sign.denominator,
                        time=self.ticks_to_eighth_notes(
                            sign.time, midi_source.resolution
                        ),
                    )
                )

        if self._sync_interval is None:
            time_signature = self._time_signatures[0]
            self._sync_interval = (
                2 * time_signature.quarters_per_bar / time_signature.beat_count
            )

        if self._verbose > 0:
            print(
                f"[INFO]\tSynchronizing every:\t{self._sync_interval/2} quarters.",
            )

        ######################### create the notes ######################

        midi_source_notes = midi_source.tracks[0].notes

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
        note_times = [
            self.ticks_to_eighth_notes(msg.time, midi_source.resolution)
            for msg in midi_source_notes
        ]
        self._score_end_time = note_times[-1] + note_durations[-1]

        # pitch, duration, note id, time
        self._score = [
            Note(pitch=p, eighth_duration=d, id=i, time=t)
            for p, d, i, t in zip(note_pitches, note_durations, note_ids, note_times)
        ]

        ############# score with repetition signs, songpos etc ###########

        self._annotated_score = []

        # add key signatures
        self._annotated_score.extend(self._key_signatures)

        # arange songpos messages independently
        songpos_timestamps = np.arange(
            start=0,
            stop=self._score_end_time,
            step=self._sync_interval,
        )
        self._annotated_score.extend(
            [SongPosition(position=p, time=t) for p, t in enumerate(songpos_timestamps)]
        )

        self.maximum_songpos = len(songpos_timestamps) - 1

        # divide messages that are longer than the sync interval
        temp_score = []
        for note in self._score:

            # split up this note
            if note.eighth_duration > self._sync_interval:
                total_duration = note.eighth_duration
                new_duration = 0
                # add a new note with the same id every sync interval
                while total_duration > 0:
                    temp_score.append(
                        Note(
                            pitch=note.pitch,
                            eighth_duration=min(self._sync_interval, total_duration),
                            id=note.id,
                            time=note.time + note.eighth_duration - total_duration,
                        )
                    )
                    total_duration -= self._sync_interval
            else:
                temp_score.append(note)

        self._annotated_score.extend(temp_score)

        self._annotated_score.sort(key=lambda x: x.time)

        # create index map to jump
        self.index_map = {}
        for i, el in enumerate(self._annotated_score):

            if isinstance(el, SongPosition):
                self.index_map[el.position] = i

        if self._verbose > 0:
            print(f"[INFO]\tPlaying:\t\t{os.path.basename(filename)}")
            print(
                f"[INFO]\tMeter:\t\t\t{self._time_signatures[0].numerator}/{self._time_signatures[0].denominator}"
            )
            print(
                f"[INFO]\tKey:\t\t\t{self._key_signatures[0].root} {self._key_signatures[0].mode}"
            )

    def ticks_to_eighth_notes(self, duration: int, ticks_per_quarter: int):
        return (
            2
            * np.round(MINIMUM_QUARTER_DIVISION * duration / ticks_per_quarter)
            / MINIMUM_QUARTER_DIVISION
        )

    @property
    def time_signature(self):
        return self._time_signatures[0]

    @property
    def key_signature(self):
        return self._current_key

    def set_key_signature(self, key):
        self._current_key = key

    @property
    def score(self):
        return self._score

    @property
    def pitches(self):
        return np.array([note.pitch for note in self._score])

    @property
    def durations(self):
        return np.array([note.eighth_duration for note in self._score])

    @property
    def times(self):
        return np.array([note.time for note in self._score])

    @property
    def tempo(self):
        return self._tempos[0]

    def get_note_by_id(self, id):
        return [note for note in self._score if note.id == id][0]

    def __len__(self) -> int:
        # return len(self._score)
        return len(self._annotated_score)

    def __getitem__(self, idx: int):
        # return self._score[idx]
        return self._annotated_score[idx]


"""
parser = argparse.ArgumentParser()
parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
args = parser.parse_args()
args = vars(args)

tune = Tune(args["source"], 1, key=None, meter=None, verbose=1, sync_interval=None)
"""
