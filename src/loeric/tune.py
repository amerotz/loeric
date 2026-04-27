import copy
import json
import os
import random

import mido
import music21 as m21
import muspy as mp
import numpy as np

from . import loeric_utils as lu


############################# CONSTANTS #########################

MINIMUM_QUARTER_DIVISION = 48
BEND_UP = 2
BEND_DOWN = 2


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


def note_list_to_midi(notes):

    midi_messages = []
    for note in notes:
        note_messages = note.to_midi(absolute_time=True)
        midi_messages.extend(note_messages)

    # sort by time
    midi_messages.sort(key=lambda x: x.time)

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
        if isinstance(value, TimeDelta):
            self._duration = copy.deepcopy(value)
        else:
            self._duration = TimeDelta(eighth_duration=value)
        if self._duration.eighth_duration < 0:
            self._duration = TimeDelta(eighth_duration=0)
            print("\033[38;2;255;255;0m[WARN]\tDuration cannot be negative!\033[0m")
            # raise Exception("Duration cannot be negative")

    def to_midi(self, absolute_time=False):
        return []


class Pause(ScoreElement):

    def __init__(self, eighth_duration, time: float = 0):
        super().__init__(time)

        self.duration = eighth_duration

    @property
    def pitch(self):
        return -1

    def __repr__(self):
        return f"(Pause {self._duration} t={self._time})"


class Chord(ScoreElement):

    def __init__(self, pitches: list, time: float = 0, is_user=False):

        super().__init__(time)

        self._number = None
        self._root = None
        self._bass = None
        self._quality = None
        self._pitches = []
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
                    self._quality, index = CHORDS[id_string]
                    self._root = pitches[i][0]
                    self._pitches = options[i]
                    self._number = self._root + 12 * index
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

    @property
    def bass(self):
        return self._bass

    @property
    def is_valid(self):
        return self._number is not None

    @property
    def chord_number(self):
        return self._number

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
        return f"(Chord {root}{self._quality}{bass} n={self._number} t={self._time})"


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

    def to_midi(self, absolute_time=False):

        time = self.duration
        if absolute_time:
            time += self._time
        return [
            mido.MetaMessage(
                "key_signature",
                key=NOTE_NAMES[self.major_root],
                time=time.eighth_duration,
            )
        ]

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

    @staticmethod
    def root_from_string(key_signature: str) -> int:
        """
        Return the tonic of a given key signature.

        :param key_signature: the key signature in the following format: [A-G](#|b)?m?
        :return: the toinc of the key signature.
        """

        base = int(m21.pitch.Pitch(key_signature[0]).ps)

        if "b" in key_signature:
            base -= 1
        elif "#" in key_signature:
            base += 1

        base += 12
        base %= 12

        return base


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
        return f"(Repetition n={self._number} t={self._time})"


class Barline(ScoreElement):

    def __init__(self, number: int = 0, time: float = 0):
        super().__init__(time)

        self._number = number

    @property
    def number(self):
        return self._number

    def __repr__(self):
        return f"(Barline n={self._number} t={self._time})"


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
        s = f"(Note p={self._pitch} {self._duration} id={self._id} t={np.round(self._time.eighth_duration, 2)} c={self.channel}"
        if self._is_slide:
            s += f",\n\tslide={self._slide_targets}"

        if self.has_metadata:
            s += " meta=["
            s += ",".join([str(m) for m in self.metadata])
            s += "]"
        s += ")"
        return s

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
        self._duration += note.duration
        duration = copy.deepcopy(self._slide_targets[0].duration)
        for note in self._slide_targets[1:]:
            duration += note.duration
        assert (
            duration <= self._duration
        ), f"Duration of targets {duration} exceeds note duration {self._duration}"

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

        bend_semitones = self._pitch - np.round(self._pitch)
        if bend_semitones > 0:
            bend_percentage = bend_semitones / BEND_UP
        else:
            bend_percentage = bend_semitones / BEND_DOWN

        messages.append(
            mido.Message(
                "pitchwheel",
                pitch=np.round(8192 * bend_percentage).astype(int),
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

            previous_bend = bend_percentage
            resolution = 24

            for note in self._slide_targets:
                slide_duration = TimeDelta(
                    eighth_duration=note.duration.eighth_duration / resolution
                )

                bend_semitones = note.pitch - self._pitch
                if bend_semitones > 0:
                    bend_percentage = bend_semitones / BEND_UP
                else:
                    bend_percentage = bend_semitones / BEND_DOWN

                # append messages
                mult = random.uniform(0.25, 0.5)
                for j in range(resolution):

                    overall_time = overall_time + slide_duration

                    perc = j / resolution
                    perc **= mult
                    pb = (1 - perc) * previous_bend + perc * bend_percentage
                    pb = min(8191, max(np.round(pb * 8191).astype(int), -8192))
                    messages.append(
                        mido.Message(
                            "pitchwheel",
                            pitch=pb,
                            channel=self.channel,
                            time=float(overall_time.eighth_duration),
                        )
                    )
                    note_duration = note_duration - slide_duration

                previous_bend = bend_percentage

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
        trim_end_eighths=0,
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
        self._filename = filename
        self._verbose = verbose
        self._sync_interval = None
        if sync_interval is not None:
            self._sync_interval = TimeDelta(eighth_duration=sync_interval)
        self._first_bar_length = 0
        self._tune_type = None
        self.repeats = repeats

        # save filename of config
        self.config = config
        self.json_config = None
        if config is not None and os.path.isfile(config):
            with open(config, "r") as f:
                # keep a loaded version for the server
                self.json_config = json.load(f)

        if filename.endswith(".mid") or filename.endswith(".midi"):
            midi_source = mp.read_midi(filename)
        elif filename.endswith(".mxl"):
            midi_source = mp.read_musicxml(filename)
            self._first_bar_length = (
                midi_source.barlines[1].time - midi_source.barlines[0].time
            ) / 12

            # TODO obtain tune type
            self._tune_type = None
        elif filename.endswith(".abc"):
            midi_source = mp.read_abc(filename)
            self._first_bar_length = (
                midi_source.barlines[1].time - midi_source.barlines[0].time
            ) / 12

            # TODO obtain tune type
            self._tune_type = None
        else:
            raise Exception(
                f"Cannot read {filename}. Make sure it is a MIDI or ABC file."
            )

        print(midi_source)
        ############################# tempo #############################

        self._tempos = [
            Tempo(
                qpm=t.qpm,
                time=self.ticks_to_eighth_notes(t.time, midi_source.resolution),
            )
            for t in midi_source.tempos
        ]
        self._current_tempo = self._tempos[0]

        ######################### key signature #########################

        # key signature
        self.forced_key = False
        self._key_signatures = []
        if key is not None:

            root, mode = tuple(key.split(" "))

            self._key_signatures.append(
                KeySignature(
                    root=KeySignature.root_from_string(root), mode=mode, time=0
                )
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
                time_signature.eighths_per_bar / time_signature.beat_count
            )

        self._first_bar_length %= self.time_signature.eighths_per_bar.eighth_duration
        if self._verbose > 0:
            print(
                f"[INFO]\tSynchronizing every:\t{self._sync_interval/2} quarters.",
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
            Barline(number=i, time=t) for i, t in enumerate(barline_times)
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
            Chord(pitches=p, time=t, is_user=True)
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
        self._score = [
            Note(pitch=p, eighth_duration=d, id=i, time=t)
            for p, d, i, t in zip(note_pitches, note_durations, note_ids, note_times)
        ]

        ######################### handle repetitions ######################

        # add repetitions
        score_duration = self._score[-1].time + self._score[-1].duration

        tmp_score = []
        repetitions = []
        chords = []
        key_signatures = []
        tempos = []
        barlines = []
        # add notes and repetitions
        for r in range(repeats):
            new_score = copy.deepcopy(self._score)
            for n in new_score:
                n.time += score_duration * r - self._first_bar_length
            repetitions.append(
                Repetition(number=r + 1, time=new_score[0].time.eighth_duration)
            )
            for k in self._key_signatures:
                key_signatures.append(
                    KeySignature(
                        root=k.root,
                        mode=k.mode,
                        time=(
                            k.time + score_duration * r - self._first_bar_length
                        ).eighth_duration,
                    )
                )
            for t in self._tempos:
                tempos.append(
                    Tempo(
                        qpm=t.qpm,
                        time=(
                            t.time + score_duration * r - self._first_bar_length
                        ).eighth_duration,
                    )
                )
            for b in self._barlines:
                barlines.append(
                    Barline(
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

        self._score = tmp_score
        self._original_chords = chords
        self._key_signatures = key_signatures
        self._tempos = tempos
        self._barlines = barlines

        # calculate end time for score with optional end trim
        self._score_end_time = (
            self._score[-1].time + self._score[-1].duration - trim_end_eighths
        )
        # remove anything beyond end time (actually happens only if trimming)
        self._score = [el for el in self._score if el.time < self._score_end_time]

        # recompute
        self._score_end_time = self._score[-1].time + self._score[-1].duration

        ############# score with repetition signs, songpos etc ###########

        self._chords = []  # will be calculated later

        self._annotated_score = []

        # add tempos
        print(self._tempos)
        self._annotated_score.extend(self._tempos)

        # add barlines
        self._annotated_score.extend(self._barlines)

        # add repetitions
        self._annotated_score.extend(repetitions)

        # add key signatures
        self._annotated_score.extend(self._key_signatures)

        # arange songpos messages independently
        self._position_times = np.arange(
            start=-self._first_bar_length,
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
        should_add_position = np.ones_like(song_positions).astype(bool)

        self._annotated_score.extend(song_positions[should_add_position])
        self._annotated_score.extend(self._score)

        self._annotated_score.sort(key=lambda x: x.time)

        self.create_index_map()

        if self._verbose > 0:
            print(f"[INFO]\tPlaying:\t\t{os.path.basename(filename)}")
            print(
                f"[INFO]\tMeter:\t\t\t{self._time_signatures[0].numerator}/{self._time_signatures[0].denominator}"
            )
            print(
                f"[INFO]\tKey:\t\t\t{self._key_signatures[0].root} {self._key_signatures[0].mode}"
            )

    def create_index_map(self):
        # create index map to jump
        self.index_map = {}
        contour_index = -1
        for i, el in enumerate(self._annotated_score):

            # if song position add it
            if isinstance(el, SongPosition):
                self.index_map[el.position] = (i, contour_index)
            """
            # if song position inside a note
            elif isinstance(el, Note) and el.has_metadata:
                for m in el.metadata:
                    if isinstance(m, SongPosition):
                        self.index_map[m.position] = (i, contour_index)
            """

            if el.is_note:
                contour_index += 1

    def ticks_to_eighth_notes(self, duration: int, ticks_per_quarter: int):
        return (
            2
            * np.round(MINIMUM_QUARTER_DIVISION * duration / ticks_per_quarter)
            / MINIMUM_QUARTER_DIVISION
        )

    def calculate_chords(
        self,
        chord_score: np.array,
        chords_per_bar: int = 2,
        allowed_chords: np.array = np.zeros(12),
    ):

        pitches = self.pitches
        notes = pitches % 12

        # message length
        lengths = np.array([n.eighth_duration for n in self.durations])
        times = np.array([t.eighth_duration for t in self.times])

        t = times.min()

        key_changes = self.key_signatures
        self._chords = copy.deepcopy(self._original_chords)
        chord_changes = self._chords

        current_key = None
        current_chord = None

        calculated_chords = []

        while t <= times.max():
            start = t
            stop = self.time_signature.eighths_per_bar / chords_per_bar + t
            if t < 0:
                stop = 0

            while len(chord_changes) != 0 and t >= chord_changes[0].time:
                current_chord = chord_changes[0]
                chord_changes = chord_changes[1:]

            while len(key_changes) != 0 and t >= key_changes[0].time:
                current_key = key_changes[0]
                key_changes = key_changes[1:]

            indexes = np.where((times >= start) & (times < stop))

            if current_chord is None or not current_chord.is_valid:
                # select bar range
                bar_notes = notes[indexes].astype(int)
                bar_lengths = lengths[indexes]

                # init counts
                chords = np.zeros(12)
                note_count = np.zeros(12)

                # add chord score for each note
                for i, n in enumerate(bar_notes):
                    chords += np.roll(chord_score, n) * bar_lengths[i]
                    note_count[n % 12] += 1

                # filter out chords that are not allowed
                chords_filtered = np.multiply(
                    chords,
                    np.roll(allowed_chords, current_key.root),
                )

                # choose the chord with the highest score
                root = np.random.choice(
                    np.argwhere(chords_filtered == chords_filtered.max())[0]
                )

                # check if the selected chord should be major according to the mode
                chord_quality = np.roll(lu.chord_quality, current_key.major_root)[root]

                harmony_value = root

                # check if the note score suggests major chord
                if note_count[(root + 4) % 12] > note_count[(root + 3) % 12]:
                    chord_quality = 0
                # check if the note score suggests minor chord
                elif note_count[(root + 3) % 12] > note_count[(root + 4) % 12]:
                    chord_quality = 1

                # check if the note score suggests diminished chord
                if (
                    note_count[(root + 6) % 12] > 2 * note_count[(root + 7) % 12]
                    and chord_quality == 1
                ):
                    chord_quality = 2

                # check if the note score suggests augmented chord
                elif (
                    note_count[(root + 8) % 12] > 2 * note_count[(root + 7) % 12]
                    and chord_quality == 0
                ):
                    chord_quality = 3

                # check if the note score suggests minor seventh chord
                elif (
                    note_count[(root + 10) % 12] > 2 * np.mean(note_count)
                    and note_count[(root + 10) % 12] > note_count[(root + 11) % 12]
                ):
                    chord_quality += 4

                # check if the note score suggests major seventh chord
                elif (
                    note_count[(root + 11) % 12] > 2 * np.mean(note_count)
                    and note_count[(root + 11) % 12] > note_count[(root + 10) % 12]
                ):
                    chord_quality += 6

                harmony_value = root + 12 * chord_quality
                new_chord = Chord.from_harmony(harmony_value)
                new_chord.time = start
                calculated_chords.append(new_chord)

            t = stop

        # add chords
        calculated_chords.extend([c for c in self._chords if c.is_valid])
        calculated_chords.sort(key=lambda x: x.time)
        self._chords = calculated_chords

        # remove all chords from score
        self._annotated_score = list(
            filter(lambda x: not isinstance(x, Chord), self._annotated_score)
        )
        calculated_chords.extend(self._annotated_score)
        calculated_chords.sort(key=lambda x: x.time)
        self._annotated_score = calculated_chords

        self._current_chord = self._chords[0]

        # update map
        self.create_index_map()

    @property
    def time_signature(self):
        return self._time_signatures[0]

    @property
    def key_signature(self):
        return self._current_key

    @property
    def key_signatures(self):
        return self._key_signatures

    @property
    def chords(self):
        return self._chords

    def set_key_signature(self, key):
        self._current_key = key

    def set_tempo(self, tempo):
        self._current_tempo = tempo

    def set_chord(self, chord):
        self._current_chord = chord

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
        return self._current_tempo

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
