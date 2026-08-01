import copy

import numpy as np
from pydantic import field_validator

import loeric.core.element as le
import loeric.core.modules.base as lmb


class HarmonyConfig(lmb.ModuleConfig):
    """Config for :class:`HarmonyModule`.

    :param chord_score: 12-element list scoring chord roots.
    :param chords_per_bar: how many chords to generate per bar.
    :param weights: mapping of mode names to 12-element weight arrays.
    """

    chord_score: list[float]
    chords_per_bar: float
    weights: dict[str, list[float]]

    @field_validator("chord_score")
    @classmethod
    def twelve_elements(cls, v: list) -> list:
        if len(v) != 12:
            raise ValueError(f"chord_score must have 12 elements, got {len(v)}")
        return v

    @field_validator("weights")
    @classmethod
    def weights_twelve_elements(cls, v: dict) -> dict:
        for name, w in v.items():
            if len(w) != 12:
                raise ValueError(
                    f"weights['{name}'] must have 12 elements, got {len(w)}"
                )
        return v


class HarmonyModule(lmb.LOERICModule):

    config_class = HarmonyConfig

    def __init__(
        self, chord_score: list[float], chords_per_bar: float, weights: dict, **kwargs
    ):
        super().__init__(**kwargs)

        self._name = "harmony"
        self._last_computation_time = -np.inf
        self._window_size = None

        self._chords_per_bar = chords_per_bar
        self._chord_score = np.array(chord_score)
        self._weights = weights
        for w in self._weights:
            self._weights[w] = np.array(self._weights[w])

        # 0 = major
        # 1 = minor
        # 2 = diminished
        # 3 = augmented
        # ####################### C C#  D Eb  E  F F#  G G#  A A#  B
        self._chord_qualities = np.array([0, 2, 1, 2, 1, 0, 2, 0, 2, 1, 0, 2])
        self._last_forced_chord = None

    def reset(self):
        super().reset()

        self._window_size = None

    @property
    def window_size(self):
        if self._time_signature is not None:
            c_per_bar = self._chords_per_bar
            if c_per_bar is None:
                c_per_bar = self._time_signature.beat_count
            self._window_size = self._time_signature.eighths_per_bar / c_per_bar
            return self._window_size
        else:
            return None

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Transpose notes.

        :param element: the element to process.
        """
        accidentals = []
        if isinstance(element, le.Chord):
            self._last_forced_chord = copy.copy(element)

            if self._last_forced_chord.is_valid:

                accidentals = self._obtain_accidentals(element)

            else:
                # filter out the null chord
                element = le.NullEvent(time=element.time)

        # only compute when reaching the interval
        should_compute = (
            self.window_size is not None
            and element.time % self._window_size == 0
            and element.is_performable
            and (
                self._last_forced_chord is None or not self._last_forced_chord.is_valid
            )
        )

        if should_compute:
            self._last_computation_time = element.time
            self._last_forced_chord = None

            # filter out elements outside required time frame
            window = [
                el
                for el in window
                if el.is_performable
                and el.time >= element.time
                and el.time < element.time + self._window_size
            ]
            chord = self._calculate_chord(window)
            chord.time = element.time

            return [*accidentals, chord, element]

        return [*accidentals, element]

    @property
    def _allowed_chords(self):
        if self._key_signature is None or self._key_signature.mode not in self._weights:
            return self._weights["default"]
        else:
            return self._weights[self._key_signature.mode]

    def _obtain_accidentals(self, element):
        accidentals = []
        chord_quality = np.roll(self._chord_qualities, self._key_signature.major_root)[
            self._last_forced_chord.root
        ]

        # propagate accidentals
        if self._last_forced_chord.quality != chord_quality:
            mode_chord = le.Chord.create_chord(
                self._last_forced_chord.root, chord_quality
            )
            # some chords are triads, some are sevenths
            chord_len = min(
                len(mode_chord.pitches), len(self._last_forced_chord.pitches)
            )
            # check degrees that are flat/sharp
            differences = (
                self._last_forced_chord.pitches[:chord_len]
                - mode_chord.pitches[:chord_len]
            )
            # create accidentals
            for alteration, degree in zip(differences, mode_chord.pitches[:chord_len]):
                if alteration == 0:
                    continue
                p = (self._last_forced_chord.root + degree) % 12
                accidentals.append(
                    le.Accidental(pitch=p, alteration=alteration, time=element.time)
                )
        return accidentals

    def _calculate_chord(self, window):

        pitches = np.array([el.pitch for el in window])
        bar_notes = (pitches % 12).astype(int)
        bar_lengths = np.array([el.duration.eighth_duration for el in window])

        # init counts
        chords = np.zeros(12)
        note_count = np.zeros(12)

        # add chord score for each note
        for i, n in enumerate(bar_notes):
            chords += np.roll(self._chord_score, n) * bar_lengths[i]
            note_count[n % 12] += 1

        # filter out chords that are not allowed
        chords_filtered = np.multiply(
            chords,
            np.roll(self._allowed_chords, self._key_signature.root),
        )

        # choose the chord with the highest score
        root = np.random.choice(
            np.argwhere(chords_filtered == chords_filtered.max())[0]
        )

        # check chord quality according to mode
        chord_quality = np.roll(self._chord_qualities, self._key_signature.major_root)[
            root
        ]

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

        return le.Chord.create_chord(root, chord_quality)
