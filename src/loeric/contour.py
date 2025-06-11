import mido
import numpy as np
from scipy.signal import savgol_filter

from . import tune
from . import loeric_utils as lu


class UncomputedContourError(Exception):
    """Raised if the contour has not been computed yet."""

    pass


class InvalidRecipeError(Exception):
    """Raised if the contour recipe is invalid."""

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

    def __getitem__(self, index):
        """
        The length of this contour.
        """
        return self._contour[index]

    def calculate(self, midi: tune.Tune) -> None:
        """
        Calculate the intensity contour for the given tune.

        :param midi: the input tune.
        """
        pass

    def jump(self, index: int) -> None:
        """
        Jump to the specified index in the contour.

        :param index: the index to jump to.
        :raise contour.InvalidIndexError: if the index exceeds the length of the contour.
        """

        if index >= len(self._contour):
            raise InvalidIndexError(
                f"Cannot jump to index {index} with contour length {len(self._contour)}"
            )
        else:
            self._index = index

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
            raise InvalidIndexError(
                f"Cannot index contour with length {len(self._contour)} with index {self._index}."
            )
        return self._contour[self._index]

    def reset(self) -> None:
        """
        Resets the contour iteration. The next call to `next()` will return the first element of the contour.
        """
        self._index = -1

    def scale_and_savgol(
        self, array: np.ndarray, savgol: bool = True, shift: bool = False, scale=False
    ) -> np.ndarray:
        """
        Scale the contour to have it range between 0 and 1.
        Optionally, apply a Savitzky-Golay filter with a window of 15 and order 3.
        Optionally, rescale the array to bring the extremes to 0 and 1.
        Optionally, shift the array to bring its mean closer to 0.5.

        :param array: the input contour.
        :param savgol: whether or not to apply the savgol filter.
        :param scale: whether or not to rescale the array to use the full range.
        :param shift: whether or not to shift the filtered array so that its mean is close to 0.5.

        :return: the processed array.
        """

        # this is a mandatory scaling step, since the contour needs
        # to have range 0 to 1
        array -= min(array)
        array /= max(array)

        if savgol:
            window = 15
            array = np.pad(array, (window, window), "mean")
            array = savgol_filter(array, window, 3)
            array = array[window:-window]

        if scale:
            array -= min(array)
            array /= max(array)

        if shift:
            array /= 2 * array.mean()

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

        notes = pitches % 12

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

            # add chord score for each note
            for i, n in enumerate(bar_notes):
                chords += np.roll(chord_score, n)  # * bar_lengths[i]

            # filter out chords that are not allowed
            root_chord = np.multiply(
                chords,
                np.roll(allowed_chords, midi.root),
            )
            # choose the chord with the highest score
            root = np.random.choice(np.argwhere(root_chord == root_chord.max())[0])

            # check if the selected chord should be major according to the mode
            chord_quality = np.roll(lu.chord_quality, midi.major_root)[root]

            harmony_value = root

            # check if the note score suggests minor chord
            # (e.g. minor IV etc, minor V, etc)
            if chords[(root + 3) % 12] > chords[(root + 4) % 12]:
                # if not diminished already
                if chord_quality != 2:
                    # make it minor
                    chord_quality = 1

            # check if the note score suggests diminished chord
            if chords[(root + 6) % 12] > chords[(root + 7) % 12]:
                chord_quality = 2

            """
            # check if the note score suggests augmented chord
            if chords[(root + 8) % 12] > chords[(root + 7) % 12]:
                chord_quality = 3
            """

            harmony_value = root + 12 * chord_quality

            # assign chord to notes in bar interval
            harmony[indexes] = harmony_value

            t = stop

        self._contour = harmony


class RandomContour(Contour):
    """A randomly initialized contour."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tune.Tune, min: float = 0, max: float = 1) -> None:
        """
        Compute a random contour following a uniform distribution in the specified range, by default between 0 and 1.

        :param midi: the input tune.
        :param extremes: the upper and lower bound for the random contour. If None, the range will be (0, 1).
        """
        note_events = midi.filter(lambda x: lu.is_note_on(x))
        size = len(note_events)
        r_min = min
        r_max = max
        self._contour = np.random.uniform(r_min, r_max, size=size)


class PhraseContour(Contour):
    """A contour representing phrase arcs."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tune.Tune, phrase_levels=2, phrase_exp=100) -> None:
        """
        Compute a phrasing contour using a sum of sine functions.

        :param midi: the input tune.
        """
        # retrieve pitch and time info
        note_events = midi.filter(lambda x: "note" in x.type)
        timings = np.array([msg.time for msg in note_events])
        pitches = np.array([msg.note for msg in note_events if lu.is_note_on(msg)])

        # cumulative time
        note_ons = np.array([lu.is_note_on(msg) for msg in note_events])
        note_offs = np.array([not lu.is_note_on(msg) for msg in note_events])
        summed_timings = np.cumsum(timings)
        summed_timings -= midi.offset
        summed_timings = summed_timings[note_ons]

        bar_length = midi.bar_duration

        self._contour = self.scale_and_savgol(
            1
            - np.cos((np.pi * summed_timings * 2 ** (phrase_levels - 1)) / bar_length)
            ** phrase_exp,
            savgol=False,
            shift=False,
            scale=True,
        )


class IntensityContour(Contour):
    """A contour given by the weighted sum of O'Canainn components."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
        weights: list = None,
        savgol: bool = True,
        shift: bool = False,
        scale: bool = False,
    ) -> None:
        """
        Compute the contour as the weighted sum of O'Canainn component.
        An optional random component can be added.

        :param midi: the input tune.
        :param weights: the weights for the components, respectively frequency score, beat score, ambitus score, leap score and length score.
        :param savgol: whether or not to apply a final savgol filtering step (recommended).
        :param shift: whether or not to apply a final shifting step to bring the mean of the array close to 0.5.
        """

        weights = np.array(weights).astype(float)

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
            indexes = np.argwhere(weights < 0)
            weights = abs(weights)
            weights /= weights.sum()

        # weight them
        stacked_components[indexes] *= -1
        stacked_components[indexes] += 1
        stacked_components = np.multiply(stacked_components, weights)
        # sum them
        stacked_components = stacked_components.sum(axis=0)

        self._contour = stacked_components

        # savgol filtering
        self._contour = self.scale_and_savgol(
            self._contour, savgol=savgol, shift=shift, scale=scale
        )

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

        note_events = midi.filter(lambda x: lu.is_note(x))
        timings = np.array([msg.time for msg in note_events])
        note_ons = np.array([lu.is_note_on(msg) for msg in note_events])
        note_offs = np.array([lu.is_note_off(msg) for msg in note_events])
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
        scale: bool = True,
    ) -> None:
        note_events = midi.filter(lambda x: "note" in x.type)
        pitches = np.array(
            [msg.note for msg in note_events if lu.is_note_on(msg)]
        ).astype(float)
        self._contour = pitches

        if savgol or shift or scale:
            self._contour = self.scale_and_savgol(
                self._contour, savgol=savgol, shift=shift, scale=scale
            )


class PatternContour(Contour):
    """A contour made of a repeating pattern."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tune.Tune,
        mean: list = [1],
        std: list = [0],
        std_scale: float = 1,
        normalize: bool = False,
        period: float = 0.5,
    ) -> None:
        """
        Create the contour by repeating the input weights over the specified period.
        If standard deviatons are specified, the resulting patter is sampled from each distribution at each loaction.

        :param mean: the pattern to repeat.
        :param std: the std of the pattern to repeat, for every item.
        :param period: the length of the pattern, in bars.
        """
        assert len(mean) == len(std)

        mean = np.array(mean).astype(float)
        std = np.array(std).astype(float)

        # retrieve pitch and time info
        note_events = midi.filter(lambda x: "note" in x.type)
        timings = np.array([msg.time for msg in note_events])
        pitches = np.array([msg.note for msg in note_events if lu.is_note_on(msg)])

        # cumulative time
        note_ons = np.array([lu.is_note_on(msg) for msg in note_events])
        note_offs = np.array([not lu.is_note_on(msg) for msg in note_events])
        summed_timings = np.cumsum(timings)
        summed_timings -= midi.offset
        summed_timings = summed_timings[note_ons]

        bar_position = summed_timings / midi.bar_duration

        pattern_indexes = np.round(
            len(mean) * (summed_timings % midi.bar_duration) / midi.bar_duration
        ).astype(int) % len(mean)
        diff = np.diff(pattern_indexes)
        index_diff = np.argwhere(diff > 1)

        pattern_means = mean[pattern_indexes].astype(float)
        pattern_stds = std[pattern_indexes].astype(float)

        for index in index_diff:
            source_index = pattern_indexes[index]
            add_indexes = np.arange(source_index, source_index + diff[index])
            pattern_means[index] = np.mean(mean[add_indexes])
            pattern_stds[index] = np.mean(std[add_indexes])

        pattern = np.random.normal(
            loc=pattern_means, scale=std_scale * pattern_stds, size=len(pattern_means)
        )

        if normalize:
            bars = summed_timings // midi.bar_duration

            for i in np.unique(bars):

                indexes = np.argwhere(bars == i)
                min_i = min(indexes)
                max_i = min(max(indexes) + 1, len(summed_timings) - 1)
                bar_sum = summed_timings[max_i] - summed_timings[min_i]
                pattern[indexes] /= pattern[indexes].sum()
                pattern[indexes] *= len(indexes)

        self._contour = pattern


def multiply(contours: list[Contour] = []) -> Contour:
    """
    Returns a new contour that holds the product of the input contours.

    :param contours: the contours to multiply.

    :return: a new contour holding the product of the input contours.
    """
    new_contour = Contour()
    result = np.ones(len(contours[0]))
    for c in contours:
        result = np.multiply(result, c._contour)
    new_contour._contour = result

    return new_contour


def weighted_sum(contours: list[Contour] = [], weights: list = []) -> Contour:
    """
    Returns a new contour that holds the weighted sum of the input contours.

    :param contours: the contours to add.
    :param weights: the weight for each contour.

    :return: a new contour holding the weighted sum of the input contours.
    """
    assert len(contours) == len(weights)

    result = np.zeros(len(contours[0]))
    size = len(contours)
    weights = np.array(weights)

    if weights is None:
        weights = np.ones((size, 1)) / size
    else:
        if weights.shape != (size, 1):
            weights = weights.reshape(size, 1)
        indexes = np.argwhere(weights < 0)
        weights = abs(weights)
        weights /= weights.sum()

    stacked_components = np.stack([c._contour for c in contours])

    # invert negative ones
    stacked_components[indexes] *= -1
    stacked_components[indexes] += 1

    # weight them
    stacked_components = np.multiply(stacked_components, weights)
    # sum them
    result = stacked_components.sum(axis=0)

    new_contour = Contour()
    new_contour._contour = result

    return new_contour


def linear_transform(contours: Contour = None, a: float = 1, b: float = 0) -> Contour:
    """
    Apply a linear transformation of the input contour f(x)= ax + b.

    :param contour: the input contour.
    :param a: the slope.
    :param b: the intercept.

    :return: the linear transformation of the input contour.
    """
    assert len(contours) == 1
    new_contour = Contour()
    new_contour._contour = a * contours[0]._contour + b
    return new_contour


def shift(contours: Contour = None, offset: int = -1) -> Contour:
    """
    Shift the contour by offset.

    :param contour: the input contour.
    :param offset: the offset of the contour, in note indexes.

    :return: the shifted input contour.
    """
    assert len(contours) == 1
    new_contour = Contour()
    new_contour._contour = np.roll(contours[0]._contour, offset)
    return new_contour


def create_contour(tune: tune.Tune, contour_program: dict, key=None) -> Contour:
    """
    Programmatically create a contour given its definition.

    :param tune: the input tune for the contour.
    :param contour_program: the dictionary containing the contour definition.

    :return: the final assembled contour.
    """

    eval_dict = {
        "o_canainn": IntensityContour,
        "pitch": PitchContour,
        "phrasing": PhraseContour,
        "random": RandomContour,
        "pattern": PatternContour,
    }

    operation_dict = {
        "weighted_sum": weighted_sum,
        "multiply": multiply,
        "linear": linear_transform,
        "shift": shift,
    }

    # check
    if key is None:
        c = list(contour_program.keys())
        if len(c) != 1:
            raise InvalidRecipeError(
                f"Only one contour can be provided. Make sure that 'recipe' only has one item in the configuration file."
            )
        c = c[0]
        return create_contour(tune, contour_program[c], key=c)

    # create the contour, leaf
    elif key in eval_dict:
        contour = eval_dict[key]()
        contour.calculate(tune, **contour_program)
        return contour

    # aggregate calculated contours
    elif key in operation_dict:

        all_contours = []

        for c in contour_program["contours"]:
            all_contours.append(
                create_contour(tune, contour_program["contours"][c], key=c)
            )

        contour_program["contours"] = all_contours
        return operation_dict[key](**contour_program)

    else:
        raise InvalidRecipeError(
            f"Recipe argument {key} is invalid. Check your configuration file."
        )
