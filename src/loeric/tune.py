import argparse
import copy
import random
import os
import numpy as np
import muspy as mp
import mido

from . import loeric_utils as lu

############################# CONSTANTS #########################

MINIMUM_QUARTER_DIVISION = 48


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


class TimeDelta:

    def __init__(self, eighth_duration):
        if isinstance(eighth_duration, int) or isinstance(eighth_duration, float):
            self._eighth_duration = TimeDelta.quantize(eighth_duration)
            if self._eighth_duration != 0:
                self._absolute_duration = 8 / self._eighth_duration
        else:
            raise Exception(
                f"Only ints and float are valid TimeDelta durations, not {type(eighth_duration)}"
            )

    @property
    def eighth_duration(self):
        return self._eighth_duration

    def __repr__(self):
        return f"d={np.round(self._eighth_duration, 4)}"

    @eighth_duration.setter
    def eighth_duration(self, value):
        self._eighth_duration = TimeDelta.quantize(value)
        if self._eighth_duration != 0:
            self._absolute_duration = 8 / self._eighth_duration

    @property
    def absolute_duration(self):
        return self._absolute_duration

    @property
    def divisions(self):
        return np.round(2 * self._eighth_duration * MINIMUM_QUARTER_DIVISION)

    @staticmethod
    def quantize(value):
        return np.round(value * MINIMUM_QUARTER_DIVISION / 2) / (
            MINIMUM_QUARTER_DIVISION / 2
        )

    def __add__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration + other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration + other.eighth_duration
            )

    def __sub__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration - other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration - other.eighth_duration
            )

    def __mul__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration * other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration * other.eighth_duration
            )

    def __truediv__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration / other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration / other.eighth_duration
            )

    def __mod__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration % other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration % other.eighth_duration
            )

    def __iadd__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration + other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration + other.eighth_duration
            )

    def __isub__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration - other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration - other.eighth_duration
            )

    def __imul__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration * other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration * other.eighth_duration
            )

    def __itruediv__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return TimeDelta(eighth_duration=self._eighth_duration / other)
        else:
            return TimeDelta(
                eighth_duration=self._eighth_duration / other.eighth_duration
            )

    def __lt__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return self._eighth_duration < other
        else:
            return self._eighth_duration < other.eighth_duration

    def __gt__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return self._eighth_duration > other
        else:
            return self._eighth_duration > other.eighth_duration

    def __le__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return self._eighth_duration <= other
        else:
            return self._eighth_duration <= other.eighth_duration

    def __ge__(self, other):
        return self._eighth_duration >= other.eighth_duration

    def __eq__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return self._eighth_duration == other
        else:
            return self._eighth_duration == other.eighth_duration

    def __ne__(self, other):
        if isinstance(other, int) or isinstance(other, float):
            return self._eighth_duration != other
        else:
            return self._eighth_duration != other.eighth_duration

    def __neg__(self):
        return TimeDelta(eighth_duration=-self._eighth_duration)


class ScoreElement:

    def __init__(self, time: float = 0):
        self._time = TimeDelta(eighth_duration=time)
        self._is_note = False
        self._duration = TimeDelta(eighth_duration=0)

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, value):
        if isinstance(value, int) or isinstance(value, float):
            self._time = TimeDelta(eighth_duration=value)
        else:
            self._time = TimeDelta(eighth_duration=value.eighth_duration)

    @property
    def is_note(self):
        return self._is_note

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        self._duration = TimeDelta(eighth_duration=value)


class Pause(ScoreElement):

    def __init__(self, eighth_duration, time: float = 0):
        super().__init__(time)

        self.duration = eighth_duration

    @property
    def pitch(self):
        return -1

    def __repr__(self):
        return f"(Pause {self._duration} t={self._time})"

    def to_midi(self, absolute_time=False):
        time = self.duration
        if absolute_time:
            time += self._time

        return [mido.Message("note_off", note=0, time=time.eighth_duration)]


class SongPosition(ScoreElement):

    def __init__(self, position: int = 0, time: float = 0):
        super().__init__(time)

        self._position = position
        self._is_note = False

    @property
    def position(self):
        return self._position

    def __repr__(self):
        return f"(Position p={self._position} t={self._time})"

    def to_midi(self, absolute_time=False):

        time = self.duration
        if absolute_time:
            time += self._time
        return [mido.Message("songpos", pos=self._position, time=time.eighth_duration)]


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

    def to_midi(self, absolute_time=False):

        time = self.duration
        if absolute_time:
            time += self._time
        names = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
        return [
            mido.MetaMessage(
                "key_signature", key=names[self.major_root], time=time.eighth_duration
            )
        ]

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
        self._eighths_per_bar = TimeDelta(eighth_duration=8 * numerator / denominator)

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
    def eighths_per_bar(self):
        return self._eighths_per_bar

    @property
    def beat_count(self):
        return self._beat_count

    @property
    def meter_string(self):
        return f"{self._numerator}/{self._denominator}"

    def __repr__(self):
        return f"(TimeSignature {self.meter_string} t={self._time})"


class Repetition(ScoreElement):

    def __init__(self, number: int = 0, time: float = 0):
        super().__init__(time)

        self._number = number

    @property
    def number(self):
        return self._number

    def __repr__(self):
        return f"(Repetition n={self._number} t={np.round(self._time, 4)})"


"""
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

"""


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

        self._duration = TimeDelta(eighth_duration=eighth_duration)

        self._id = id
        self._velocity = velocity
        self._is_slide = slide
        self._slide_targets = []
        self.channel = channel
        self._is_note = True
        self._metadata = []

    def __repr__(self):
        return f"(Note p={self._pitch} {self._duration} id={self._id} t={self._time})"

    def add_metadata(self, data):
        self._metadata.append(data)

    @property
    def has_metadata(self):
        return len(self._metadata) != 0

    @property
    def metadata(self):
        return self._metadata

    def transpose(self, semitones):
        self._pitch += semitones
        if self._is_slide:
            for note in self._slide_targets:
                note.transpose(semitones)

    def add_slide_target_pitch(self, note):
        if not self._is_slide:
            raise Exception(
                "slide not permitted. This note was created with slide=False."
            )
        self._slide_targets.append(note)
        # print(self._pitch, self._slide_targets, self._eighth_duration)
        duration = self._slide_targets[0].duration
        for note in self._slide_targets[1:]:
            duration += note.duration
        """
        assert (
            duration <= self._duration
        ), f"Duration of targets {duration} exceeds note duration {self._duration}"
        """

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        original_duration = self._duration.eighth_duration
        self._duration = value

        if self._is_slide:
            ratio = value / original_duration
            for note in self._slide_targets:
                note.duration = note.duration * ratio

    @property
    def pitch(self):
        return self._pitch

    @property
    def id(self):
        return self._id

    def to_midi(self, absolute_time=False):

        overall_time = TimeDelta(eighth_duration=0)
        if absolute_time:
            overall_time = TimeDelta(eighth_duration=self._time.eighth_duration)

        messages = []
        messages.append(
            mido.Message(
                "pitchwheel",
                pitch=np.round(8192 * (np.round(self._pitch) - self._pitch)).astype(
                    int
                ),
                channel=self.channel,
                time=overall_time.eighth_duration,
            )
        )
        messages.append(
            mido.Message(
                "note_on",
                note=np.round(self._pitch).astype(int),
                time=overall_time.eighth_duration.astype(float),
                channel=self.channel,
                velocity=self._velocity,
            )
        )

        note_duration = TimeDelta(eighth_duration=self._duration.eighth_duration)
        if self._is_slide:

            previous_bend = 0
            resolution = 24

            for note in self._slide_targets:
                slide_duration = TimeDelta(
                    eighth_duration=note.duration.eighth_duration / resolution
                )

                bend = max(
                    min(4096.0 * (note.pitch - self._pitch), 8191),
                    -8192,
                )
                # print(previous_bend, bend)

                # append messages
                mult = random.uniform(0.25, 0.5)
                for j in range(resolution):
                    if absolute_time:
                        overall_time = overall_time + slide_duration
                    perc = j / resolution
                    perc **= mult
                    pb = (1 - perc) * previous_bend + perc * bend
                    pb = int(pb)
                    messages.append(
                        mido.Message(
                            "pitchwheel",
                            pitch=pb,
                            channel=self.channel,
                            time=overall_time.eighth_duration.astype(float),
                        )
                    )
                    note_duration = note_duration - slide_duration

                previous_bend = bend

        if self._duration == 0:
            note_duration += 0.001

        messages.append(
            mido.Message(
                "note_off",
                note=np.round(self._pitch).astype(int),
                channel=self.channel,
                time=(overall_time + note_duration).eighth_duration.astype(float),
                velocity=0,
            )
        )
        return messages


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
        self._first_bar_length = 0
        self._tune_type = None

        if filename.endswith(".mid") or filename.endswith(".midi"):
            midi_source = mp.read_midi(filename)
        elif filename.endswith(".abc"):
            midi_source = mp.read_abc(filename)
            self._first_bar_length = (
                midi_source.barlines[1].time - midi_source.barlines[0].time
            ) / 12

            # TODO obtain tune type
            self._tune_type = None
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
                print(key)
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
                time_signature.eighths_per_bar / time_signature.beat_count
            )

        if self._verbose > 0:
            print(
                f"[INFO]\tSynchronizing every:\t{self._sync_interval/2} quarters.",
            )

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
        self._score = [
            Note(pitch=p, eighth_duration=d, id=i, time=t)
            for p, d, i, t in zip(note_pitches, note_durations, note_ids, note_times)
        ]

        # add repetitions
        score_duration = self._score[-1].time + self._score[-1].duration

        tmp_score = []
        # add notes and repetitions
        for r in range(repeats):
            new_score = copy.deepcopy(self._score)
            for n in new_score:
                n.time += score_duration * r - self._first_bar_length
            tmp_score.extend(new_score)

        self._score = tmp_score
        self._score_end_time = self._score[-1].time + self._score[-1].duration

        ############# score with repetition signs, songpos etc ###########

        self._annotated_score = []

        # add key signatures
        self._annotated_score.extend(self._key_signatures)

        # arange songpos messages independently
        self._position_times = np.arange(
            start=0,
            stop=self._score_end_time.eighth_duration,
            step=self._sync_interval.eighth_duration,
        )
        song_positions = np.array(
            [
                SongPosition(position=p, time=t)
                for p, t in enumerate(self._position_times)
            ]
        )

        self.maximum_songpos = len(self._position_times) - 1

        # divide add songpos in messages that contain a sync interval
        notes_to_add = []
        should_add_position = np.ones_like(song_positions).astype(bool)
        for note in self._score:

            note_start = note.time
            note_end = note.time + note.duration
            for i, position in enumerate(song_positions):

                timestamp = position.time
                # if timestamp contained in note
                if note_start < timestamp and timestamp < note_end:
                    note.add_metadata(position)
                    should_add_position[i] = False

        self._annotated_score.extend(song_positions[should_add_position])
        self._annotated_score.extend(self._score)

        self._annotated_score.sort(key=lambda x: x.time)

        # create index map to jump
        self.index_map = {}
        contour_index = -1
        for i, el in enumerate(self._annotated_score):

            if isinstance(el, SongPosition):
                self.index_map[el.position] = (i, contour_index)

            if el.is_note:
                contour_index += 1

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
    def name(self) -> str:
        return os.path.basename(self._filename)

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
        return np.array([note.duration for note in self._score])

    @property
    def times(self):
        return np.array([note.time for note in self._score])

    @property
    def float_times(self):
        return np.array([note.time.eighth_duration for note in self._score])

    def position_time(self, position):
        return self._position_times[position]

    @property
    def tempo(self):
        return self._tempos[0]

    @property
    def tune_type(self):
        if self._tune_type is None:
            tunes = {
                "2/2": "reel",
                "2/4": "polka",
                "3/4": "waltz",
                "4/4": "hornpipe",
                "6/8": "jig",
                "9/8": "slipjig",
                "12/8": "slide",
            }
            return tunes[self.time_signature.meter_string]
        else:
            return self._tune_type

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
