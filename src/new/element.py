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
import heapq as hq
import time

import numpy as np

import loeric.loeric_utils as lu


MINIMUM_QUARTER_DIVISION = 48
NOTE_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
CHORDS = {
    "0_4_7": ("", 0),
    "0_3_7": ("m", 1),
    "0_3_6": ("dim", 2),
    "0_4_8": ("aug", 3),
    "0_4_7_10": ("7", 4),
    "0_3_7_10": ("m7", 5),
    "0_4_7_11": ("M7", 6),
    "0_3_7_11": ("mM7", 7),
}


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
        if isinstance(other, int) or isinstance(other, float):
            return self._eighth_duration >= other
        else:
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


class LOERICElement:
    def __init__(self, time: float = 0):
        self._time = TimeDelta(eighth_duration=time)
        self._is_note = False
        self._duration = TimeDelta(eighth_duration=0)
        self._module_signatures = []

    def has_signature(self, signature):
        return signature in self._module_signatures

    def add_signature(self, signature):
        self._module_signatures.append(signature)

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
        if isinstance(value, TimeDelta):
            self._duration = copy.deepcopy(value)
        else:
            self._duration = TimeDelta(eighth_duration=value)
        if self._duration.eighth_duration < 0:
            self._duration = TimeDelta(eighth_duration=0)
            print("\033[38;2;255;255;0m[WARN]\tDuration cannot be negative!\033[0m")
            # raise Exception("Duration cannot be negative")


class NullEvent(LOERICElement):
    def __init__(self, time: float = 0):
        super().__init__(time)

    def __repr__(self):
        return f"(Null t={self._time})"


class Lookahead(LOERICElement):
    def __init__(self, eighth_duration: float = 0, time: float = 0):
        super().__init__(time)

        self.duration = eighth_duration

    def __repr__(self):
        return f"(Lookahead {self._duration})"

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        if isinstance(value, TimeDelta):
            self._duration = copy.deepcopy(value)
        else:
            self._duration = TimeDelta(eighth_duration=value)


class Pause(LOERICElement):
    def __init__(self, eighth_duration, time: float = 0):
        super().__init__(time)

        self.duration = eighth_duration

    @property
    def pitch(self):
        return -1

    def __repr__(self):
        return f"(Pause {self._duration} t={self._time})"


class EndOfScore(LOERICElement):
    def __init__(self, time: float = 0):
        super().__init__(time)

    def __repr__(self):
        return f"(EndOfScore t={self._time})"


class Chord(LOERICElement):
    def __init__(self, pitches: list, time: float = 0, is_user=False):

        super().__init__(time)

        self._root = None
        self._bass = None
        self._quality = None
        self._pitches = []
        self._id_string = None
        self.is_user = is_user

        if len(pitches) != 0:
            # bring into octave
            pitches = np.array(pitches)
            pitches %= 12
            pitches = pitches.reshape(len(pitches), 1).astype(int)

            # check for possible inversions
            options = np.repeat(pitches, len(pitches), axis=1).T
            options -= pitches
            options += 12
            options %= 12

            found = False
            for i in range(len(options)):
                # sort it to standard shape
                options[i] = np.sort(options[i])

                # if present in CHORDS
                id_string = "_".join(options[i].astype(str))
                if id_string in CHORDS:
                    # we found it!
                    self._id_string = id_string
                    self._quality, _ = CHORDS[id_string]
                    self._root = pitches[i][0]
                    self._pitches = options[i].astype(float)
                    self._bass = pitches[0][0]
                    found = True

                    break

            if not found:
                pitches = pitches.flatten()
                pitches -= min(pitches)
                pitches.sort()
                print(
                    f"\033[38;2;255;255;0m[WARN]\tChord shape {pitches} at time {self._time} not supported.\033[0m"
                )

    @property
    def root(self):
        return self._root

    def transpose(self, steps):
        self._root += steps
        self._root %= 12
        self._bass += steps
        self._bass %= 12
        self._pitches += steps
        self._pitches %= 12

    @property
    def bass(self):
        return self._bass

    @property
    def chord_number(self):
        if self._id_string is None:
            return None
        _, index = CHORDS[self._id_string]
        return self._root + 12 * index

    @property
    def pitches(self):
        return self._pitches

    @staticmethod
    def from_harmony(harmony):
        kind = harmony // 12
        root = harmony % 12
        for c in CHORDS:
            _, number = CHORDS[c]
            if kind == number:
                pitches = [(root + int(n)) % 12 for n in c.split("_")]
                return Chord(pitches=pitches)

        print(f"[WARN]\tUnknown harmony {harmony} (kind = {kind}, root = {root}).")

    def __repr__(self):
        root = "n/a"
        if self._root is not None:
            root = NOTE_NAMES[self._root]
        bass = ""
        if self._bass is not None and self._root != self._bass:
            bass = f"/{NOTE_NAMES[self._bass]} "
        return (
            f"(Chord {root}{self._quality}{bass} n={self.chord_number} t={self._time})"
        )


class SongPosition(LOERICElement):
    def __init__(self, position: int = 0, time: float = 0):
        super().__init__(time)

        self._position = position
        self._is_note = False

    @property
    def position(self):
        return self._position

    def __repr__(self):
        return f"(Position p={self._position} t={self._time})"


class Tempo(LOERICElement):
    def __init__(self, qpm: float = 0, time: float = 0):
        super().__init__(time)

        self._qpm = qpm

    @property
    def qpm(self):
        return self._qpm

    def __repr__(self):
        return f"(Tempo q={self._qpm} t={self._time})"


class UserTempo(Tempo):
    def __init__(self, qpm: float = 0, time: float = 0):
        super().__init__(qpm, time)

    def __repr__(self):
        return f"(UserTempo q={self._qpm} t={self._time})"


class KeySignature(LOERICElement):
    def __init__(self, root: int = 0, mode: str = "major", time: float = 0):
        super().__init__(time)

        self._root = root
        self._mode = mode
        self._fifths = lu.number_of_fifths[self.major_root]

    @property
    def root(self):
        return self._root

    def transpose(self, steps):
        self._root += int(steps)
        self._root %= 12
        self._fifths = lu.number_of_fifths[self.major_root]

    @property
    def mode(self):
        return self._mode

    @property
    def fifths(self):
        return self._fifths

    def __repr__(self):
        return (
            f"(KeySignature k={NOTE_NAMES[self._root]} m={self._mode} t={self._time})"
        )

    def degree_from_root(self, pitch: int, with_octave=False):

        indexes = np.argwhere(self.scale == (pitch - self.root) % 12)
        accidental = 0

        if len(indexes) == 0:
            indexes = np.argwhere(self.scale == (pitch - 1 - self._root) % 12)
            accidental = 1

        indexes = indexes[0][0]
        if with_octave:
            indexes += 7 * ((pitch - self._root) // 12)

        return int(indexes), accidental

    def degree_difference(self, pitch1, pitch2):

        a, acc1 = self.degree_from_root(pitch1, with_octave=True)
        b, acc2 = self.degree_from_root(pitch2, with_octave=True)

        is_chromatic = False
        if acc1 + acc2 != 0:
            is_chromatic = True

        return b - a, is_chromatic

    def degree_add(self, midi, degree):

        note, acc = self.degree_from_root(midi)

        midi += self.scale[int(note + degree) % 7]
        midi -= self.scale[int(note)]
        midi -= acc

        midi += 12 * ((note + degree) // 7)

        return midi

    @property
    def major_root(self) -> int:
        mode_offset = {
            "major": 0,
            "dorian": -2,
            "phrygian": -3,
            "mixolydian": 5,
            "lydian": 7,
            "minor": 3,
            "locrian": 1,
        }
        return (12 + self._root + mode_offset[self._mode]) % 12

    @property
    def scale(self):
        mode_degree = {
            "major": 0,
            "dorian": 1,
            "phrygian": 2,
            "mixolydian": 3,
            "lydian": 4,
            "minor": 5,
            "locrian": 6,
        }
        scale = np.roll(lu.major_scale, -mode_degree[self._mode])
        scale -= scale[0]
        scale += 12
        scale %= 12

        return scale


class TimeSignature(LOERICElement):
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


class Repetition(LOERICElement):
    def __init__(self, number: int = 0, time: float = 0):
        super().__init__(time)

        self._number = number

    @property
    def number(self):
        return self._number

    def __repr__(self):
        return f"(Repetition n={self._number} t={self._time})"


class Accidental(LOERICElement):
    def __init__(self, pitch: float = 0, alteration: float = 0, time: float = 0):
        super().__init__(time)

        self._pitch = pitch
        self._alteration = alteration

    @property
    def pitch(self):
        return self._pitch

    @property
    def alteration(self):
        return self._alteration

    def __repr__(self):
        return f"(Accidental p={self._pitch} a={self._alteration})"


class Barline(LOERICElement):
    def __init__(self, number: int = 0, time: float = 0):
        super().__init__(time)

        self._number = number

    @property
    def number(self):
        return self._number

    def __repr__(self):
        return f"(Barline n={self._number} t={self._time})"


class Note(LOERICElement):
    def __init__(
        self,
        pitch: float = 0,
        eighth_duration: float = 1,
        id: int = 0,
        time: float = 0,
        velocity=0.5,
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
        s = f"(Note p={self._pitch} {self._duration} id={self._id} t={np.round(self._time.eighth_duration, 2)} c={self.channel}"
        if self.is_slide:
            s += f",\n\tslide={self._slide_targets}"

        if self.has_metadata:
            s += " meta=["
            s += ",".join([str(m) for m in self.metadata])
            s += "]"
        s += ")"
        return s

    @property
    def has_metadata(self):
        return len(self._metadata) != 0

    @property
    def is_slide(self):
        return self._is_slide

    @property
    def slide_targets(self):
        return self._slide_targets

    @property
    def metadata(self):
        return self._metadata

    def transpose(self, semitones):
        self._pitch += semitones
        if self.is_slide:
            for note in self._slide_targets:
                note.transpose(semitones)

    def add_slide_target_pitch(self, note):
        if not self.is_slide:
            raise Exception(
                "slide not permitted. This note was created with slide=False."
            )
        self._slide_targets.append(note)
        self._duration += note.duration
        duration = copy.deepcopy(self._slide_targets[0].duration)
        for note in self._slide_targets[1:]:
            duration += note.duration
        assert duration <= self._duration, (
            f"Duration of targets {duration} exceeds note duration {self._duration}"
        )

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        original_duration = self._duration.eighth_duration
        if isinstance(value, TimeDelta):
            self._duration = copy.deepcopy(value)
        else:
            self._duration = TimeDelta(eighth_duration=value)

        if self.is_slide:
            ratio = value / original_duration
            for note in self._slide_targets:
                note.duration = note.duration * ratio

    @property
    def velocity(self):
        return self._velocity

    @velocity.setter
    def velocity(self, value):
        self._velocity = value

    @property
    def pitch(self):
        return self._pitch

    @property
    def id(self):
        return self._id


class Queue:
    def __init__(self):
        self._q = []

    def push(self, el):
        hq.heappush(self._q, el)

    def pop(self):
        return hq.heappop(self._q)

    def peek(self):
        return self._q[0]

    def is_empty(self):
        return len(self._q) == 0

    def __len__(self):
        return len(self._q)

    def __getitem__(self, index):
        return self._q[index]


class LOERICQueue(Queue):
    """A priority queue of LOERICElements, by time."""

    def __init__(self):
        super().__init__()
        order = [
            Lookahead,
            SongPosition,
            Barline,
            KeySignature,
            Accidental,
            TimeSignature,
            Tempo,
            UserTempo,
            Repetition,
            Chord,
            NullEvent,
            Note,
            Pause,
            EndOfScore,
        ]
        self._item_order = {el: i for i, el in enumerate(order)}

    def push(self, item: LOERICElement):
        item = copy.deepcopy(item)
        super().push(
            (
                item.time.eighth_duration,
                self._item_order[type(item)],
                time.time(),
                item,
            )
        )

    def peek(self):
        return super().peek()[-1]

    def pop(self):
        return super().pop()[-1]
