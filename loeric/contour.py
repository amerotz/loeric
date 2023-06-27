import mido
import numpy as np

import tune


class UncomputedContourError(Exception):
    """Raised if the contour has not been computed yet."""

    pass


class InvalidIndexError(Exception):
    """Raised if the index of the current value is below 0 or exceeds the length of the contour."""

    pass


class Contour:
    """A class representing a note-wise intensity conotour."""

    def __init__(self):
        """
        Initialize the class.
        """
        self._index = -1
        self._contour = None

    def calculate(self, midi: tune.Tune) -> None:
        """
        Calculate the intensity contour for the given tune.
        :params midi: the input tune.
        """
        pass

    def next(self) -> float:
        """
        Return the next element (i.e. intensity value) of the intensity contour.
        :raise contour.UncomputedContourError: if the contour has not been computed yet.
        :raise contour.InvalidIndexError: if the index of the current value is below 0 or exceeds the length of the contour.
        :return: the next intensity value.
        """
        if self._contour is None:
            raise UncomputedContourError(
                "Contour is not computed. Call calculate() first."
            )

        self._index += 1

        if self._index < 0 or self._index >= len(self._contour):
            raise InvalidIndexError("Cannot index contour.")
        return self._contour[self._index]

    def reset(self) -> None:
        """
        Resets the contour iteration. The next call to `next()` will return the first element of the contour.
        """
        self._index = -1

    def ocanainn_scores(
        self, midi: tune.Tune
    ) -> tuple[np.array, np.array, np.array, np.array, np.array]:
        """
        Computes the individual components for the ocanainn score:
        - frequency score;
        - beat score;
        - ambitus score;
        - leap score;
        - length score.
        :param midi: the input tune used to compute the individual scores.
        :return: the frequency score, the beat score, the ambitus score, the leap score and the length score.
        """
        # retrieve pitch and time info
        # note_events = [msg for msg in midi if "note" in msg.type]
        note_events = midi.filter(lambda x: "note" in x.type)
        timings = np.array([msg.time for msg in note_events])
        pitches = np.array([msg.note for msg in note_events if tune.is_note_on(msg)])

        # cumulative time
        note_ons = np.array([tune.is_note_on(msg) for msg in note_events])
        note_offs = np.array([not tune.is_note_on(msg) for msg in note_events])
        summed_timings = np.cumsum(timings)
        summed_timings -= midi.offset
        summed_timings = summed_timings[note_ons]

        # o canainn score
        notes = pitches % 12

        # frequency score
        values, counts = np.unique(notes, return_counts=True)
        frequency_score = np.array(
            [counts[np.where(values == n)] for n in notes]
        ).astype(float)
        frequency_score = frequency_score.reshape(-1)

        # strong beat
        beat_position = (summed_timings % midi.bar_duration) / midi.beat_duration
        beat_position = abs(beat_position - np.round(beat_position))
        trigger_delta = 0.05
        beats = -np.ones(notes.shape)
        indexes = np.where(beat_position <= trigger_delta)
        beats[indexes] = notes[indexes]
        values, counts = np.unique(beats, return_counts=True)
        beat_score = np.array([counts[np.where(values == n)] for n in beats]).astype(
            float
        )
        beat_score = beat_score.reshape(-1)
        beat_score[np.where(beats == -1)] = 0
        beat_score = beat_score.reshape(-1)

        # highest/lowest score
        highest = notes == max(notes)
        lowest = notes == min(notes)
        ambitus_score = (highest | lowest).astype(float)

        # leap score
        diff = np.insert(np.diff(notes), 0, 0)
        leaps = -np.ones(notes.shape)
        index = np.where(diff >= 7)
        leaps[index] = notes[index]
        values, counts = np.unique(leaps, return_counts=True)
        leap_score = np.array([counts[np.where(values == n)] for n in leaps]).astype(
            float
        )
        leap_score = leap_score.reshape(-1)
        leap_score[np.where(leaps == -1)] = 0

        # long score
        timings = timings[note_offs] - timings[note_ons]
        values, counts = np.unique(timings, return_counts=True)
        index = np.argmax(counts)
        val = values[index]
        length_score = (timings > val).astype(float)

        return frequency_score, beat_score, ambitus_score, leap_score, length_score


class RandomContour(Contour):
    """A randomly initialized contour."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tune.Tune) -> None:
        """
        Compute a random contour following a uniform distribution between 0 and 1.
        :param midi: the input tune.
        """
        note_events = midi.filter(lambda x: tune.is_note_on(x))
        size = len(note_events)
        self._contour = np.random.uniform(0, 1, size=size)
