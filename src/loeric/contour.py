import mido
import numpy as np
from scipy.signal import savgol_filter

from . import tune
from . import loeric_utils as lu


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

    def __len__(self):
        """
        The length of this contour.
        """
        return len(self._contour)

    def calculate(self, midi: tune.Tune) -> None:
        """
        Calculate the intensity contour for the given tune.

        :param midi: the input tune.
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

    def scale_and_savgol(self, array: np.ndarray, shift: bool = False) -> np.ndarray:
        """
        Scale the contour, then apply a Savitzky-Golay filter with a window of 15 and order 3.
        Optionally, shift the array to bring its mean closer to 0.5.

        :param array: the input contour.
        :param shift: whether or not to shift the filtered array so that its mean is close to 0.5.

        :return: the filtered array.
        """
        array -= min(array)
        array /= max(array)

        window = 15
        array = np.pad(array, (window, window), "mean")
        array = savgol_filter(array, window, 3)
        array = array[window:-window]

        if shift:
            array += min(0.5 - array.mean(), 1 - max(array))

        array[array < 0] = 0
        array[array > 1] = 1

        return array


class HarmonicContour(Contour):
    """A contour holding harmonic information."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
        chord_score: np.array,
        chords_per_bar: int = 2,
        allowed_chords: np.array = np.zeros(12),
        transpose: int = 0,
    ) -> None:
        # retrieve pitch and time info
        # note_events = [msg for msg in midi if "note" in msg.type]
        note_events = midi.filter(lambda x: "note" in x.type)
        timings = np.array([msg.time for msg in note_events])
        pitches = np.array([msg.note for msg in note_events if lu.is_note_on(msg)])

        # cumulative time
        note_ons = np.array([lu.is_note_on(msg) for msg in note_events])
        note_offs = np.array([not lu.is_note_on(msg) for msg in note_events])
        summed_timings = np.cumsum(timings)
        summed_timings -= midi.offset
        summed_timings = summed_timings[note_ons]

        notes = (pitches + transpose) % 12

        # message length
        lengths = timings[note_offs] - timings[note_ons]
        lengths /= midi.bar_duration
        lengths = np.interp(lengths, (0, lengths.max()), (0, 1))

        # estimate chord for each bar
        harmony = np.zeros(len(note_events))

        t = summed_timings.min()
        while t < summed_timings.max():
            start = t
            stop = t + midi.bar_duration / chords_per_bar
            if t < 0:
                stop = 0

            # select bar range
            indexes = np.where((summed_timings >= start) & (summed_timings < stop))
            bar_notes = notes[indexes]
            bar_lengths = lengths[indexes]

            # init counts
            chords = np.zeros(12)

            for i, n in enumerate(bar_notes):
                chords += np.roll(chord_score, n)  # * bar_lengths[i]

            chords = np.multiply(
                chords,
                np.roll(allowed_chords, midi.root),
            )
            root = np.random.choice(np.argwhere(chords == chords.max())[0])
            mode = "maj"
            harmony[indexes] = np.argmax(chords)

            if chords[(root + 3) % 12] > chords[(root + 4) % 12]:
                mode = "min"
                harmony[indexes] += 12

            t = stop

        self._contour = harmony


class RandomContour(Contour):
    """A randomly initialized contour."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tune.Tune, extremes: tuple[float, float] = None) -> None:
        """
        Compute a random contour following a uniform distribution in the specified range, by default between 0 and 1.

        :param midi: the input tune.
        :param extremes: the upper and lower bound for the random contour. If None, the range will be (0, 1).
        """
        note_events = midi.filter(lambda x: lu.is_note_on(x))
        size = len(note_events)
        if extremes is None:
            extremes = (0, 1)
        self._contour = np.random.uniform(*extremes, size=size)


class IntensityContour(Contour):
    """A contour given by the weighted sum of O'Canainn components."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
        weights: np.array = None,
        random_weight: float = 0,
        savgol: bool = True,
        shift: bool = False,
    ) -> None:
        """
        Compute the contour as the weighted sum of O'Canainn component.
        An optional random component can be added.

        :param midi: the input tune.
        :param weights: the weights for the components, respectively frequency score, beat score, ambitus score, leap score and length score.
        :param random_weight: the weight of the random component over the sum of the weighted O'Canainn scores. If None, the components will be averaged together.
        :param savgol: whether or not to apply a final savgol filtering step (recommended).
        :param shift: whether or not to apply a final shifting step to bring the mean of the array close to 0.5.
        """

        weights = weights.astype(float)

        # calculate the components
        components = self.ocanainn_scores(midi)
        # stack them
        stacked_components = np.stack(components, axis=0)
        size = stacked_components.shape[0]

        if weights is None:
            weights = np.ones((size, 1)) / size
        else:
            if weights.shape != (size, 1):
                weights = weights.reshape(size, 1)
            weights /= weights.sum()

        # weight them
        stacked_components = np.multiply(stacked_components, weights)
        # sum them
        stacked_components = stacked_components.sum(axis=0)

        # add the random contour
        self._contour = stacked_components
        if random_weight != 0:
            self._contour *= 1 - random_weight
            random_contour = RandomContour()
            random_contour.calculate(midi, extremes=(0, 1))
            self._contour += random_contour._contour * random_weight

        # savgol filtering
        if savgol:
            self._contour = self.scale_and_savgol(self._contour, shift=shift)

    def ocanainn_scores(
        self, midi: tune.Tune
    ) -> tuple[np.array, np.array, np.array, np.array, np.array]:
        """
        Computes the individual components for the ocanainn score:

        * frequency score;
        * beat score;
        * ambitus score;
        * leap score;
        * length score.

        :param midi: the input tune used to compute the individual scores.

        :return: the frequency score, the beat score, the ambitus score, the leap score and the length score.
        """
        # retrieve pitch and time info
        # note_events = [msg for msg in midi if "note" in msg.type]
        note_events = midi.filter(lambda x: "note" in x.type)
        timings = np.array([msg.time for msg in note_events])
        pitches = np.array([msg.note for msg in note_events if lu.is_note_on(msg)])

        # cumulative time
        note_ons = np.array([lu.is_note_on(msg) for msg in note_events])
        note_offs = np.array([not lu.is_note_on(msg) for msg in note_events])
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
        frequency_score = np.interp(
            frequency_score, (frequency_score.min(), frequency_score.max()), (0, 1)
        )

        # strong beat
        beat_position = (summed_timings % midi.bar_duration) / midi.beat_duration
        beat_position = abs(beat_position - np.round(beat_position))
        trigger_delta = lu.TRIGGER_DELTA
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
        beat_score = np.interp(beat_score, (beat_score.min(), beat_score.max()), (0, 1))

        # highest/lowest score
        highest = pitches == max(pitches)
        lowest = pitches == min(pitches)
        ambitus_score = (highest | lowest).astype(float)

        # leap score
        diff = np.diff(pitches)
        diff = np.insert(diff, 0, 0)
        leaps = -np.ones(pitches.shape)
        index = np.where(diff >= 7)
        leaps[index] = notes[index]
        values, counts = np.unique(leaps, return_counts=True)
        leap_score = np.array([counts[np.where(values == n)] for n in leaps]).astype(
            float
        )
        leap_score = leap_score.reshape(-1)
        leap_score[np.where(leaps == -1)] = 0
        if leap_score.min() != leap_score.max():
            leap_score = np.interp(
                leap_score, (leap_score.min(), leap_score.max()), (0, 1)
            )

        # long score
        timings = timings[note_offs] - timings[note_ons]
        values, counts = np.unique(timings, return_counts=True)
        index = np.argmax(counts)
        val = values[index]
        length_score = (timings > val).astype(float)

        return frequency_score, beat_score, ambitus_score, leap_score, length_score


class MessageLengthContour(Contour):
    """A contour holding the length of each note in the tune."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
    ) -> None:
        """
        Calculate the contour as the length of each note message (from each note on message to the next note off message).

        :param midi: the input tune object.
        """

        note_events = midi.filter(lambda x: "note" in x.type)
        timings = np.array([msg.time for msg in note_events])
        note_ons = np.array([lu.is_note_on(msg) for msg in note_events])
        note_offs = np.array([not lu.is_note_on(msg) for msg in note_events])
        self._contour = timings[note_offs] - timings[note_ons]


class PitchDifferenceContour(Contour):
    """A contour holding the pitch difference between notes in the tune."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
    ) -> None:
        note_events = midi.filter(lambda x: "note" in x.type)
        pitches = np.array([msg.note for msg in note_events if lu.is_note_on(msg)])
        diff = np.diff(pitches)
        diff = np.insert(diff, 0, 0)
        self._contour = diff


class PitchContour(Contour):
    """A contour holding the pitch of notes in the tune."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
        savgol: bool = True,
        shift: bool = True,
    ) -> None:
        note_events = midi.filter(lambda x: "note" in x.type)
        pitches = np.array(
            [msg.note for msg in note_events if lu.is_note_on(msg)]
        ).astype(float)
        self._contour = pitches

        if savgol:
            self._contour = self.scale_and_savgol(self._contour, shift=shift)


def weighted_sum(contours: list[Contour], weights: np.ndarray):
    """
    Returns a new contour that holds the weighted sum of the input contours.

    :param contours: the contours to add.
    :param weights: the weight for each contour.

    :return: a new contour holding the weighted sum of the input contours.
    """
    result = np.zeros(len(contours[0]))
    weights /= np.sum(weights)
    for c, w in zip(contours, weights):
        result += c._contour * w

    new_contour = Contour()
    new_contour._contour = result

    return new_contour
