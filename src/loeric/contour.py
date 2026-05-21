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

from functools import cached_property

import numpy as np
from scipy.signal import savgol_filter

import loeric.element as le
import loeric.tune as tu


class ContourManager:
    def __init__(self, config: dict, tune: tu.Tune):

        self._config = config

        # create contours
        self._contours = {}

        # for every contour c
        for c in self._config:
            print(f"[INFO]\tCreating {c} contour.")

            # create contour
            self._contours[c] = create_contour(
                tune, self._config[c]["recipe"], parent=c
            )

    def __setitem__(self, key: str, value: float):
        """Set the contour named ``key`` to ``value``."""

    def __getitem__(self, key: str):
        """Get the value of contour named ``key``."""

    @cached_property
    def contours(self):
        """Return a dictionary of all contours."""
        return self._contours

    def at(self, time: float = None):
        """Return contour values at a specific time."""
        return {c: self._contours[c].at(time) for c in self._contours}

    def reset(self):
        """Reset all variables."""


class InvalidRecipeError(Exception):
    """Raised if the contour recipe is invalid."""


class Contour:
    """A class representing a note-wise intensity conotour."""

    def __init__(self):
        """Initialize the class."""
        self._contour = None
        self._is_real_time = False

    def __len__(self):
        """The length of this contour."""
        return len(self._contour)

    @cached_property
    def is_real_time(self):
        return self._is_real_time

    @cached_property
    def values(self):
        """Return all contour values as an array"""
        return self._contour

    def calculate(self, midi: tu.Tune) -> None:
        """Calculate the intensity contour for the given tune.

        :param midi: the input tune.
        """
        self._contour_times = np.array([t.eighth_duration for t in midi.times])

    def scale_and_savgol(
        self, array: np.ndarray, savgol: bool = True, shift: bool = False, scale=False
    ) -> np.ndarray:
        """Scale the contour to have it range between 0 and 1.
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

    def at(self, time: le.TimeDelta | float | int):
        """Return the value of the contour at a specific performance time, in eighth notes."""
        time = float(time)

        index = np.argwhere(time >= self._contour_times).flatten()
        if len(index) == 0:
            return self._contour[0]
        else:
            index = index[-1]
        return self._contour[index]

        return value


class CompositeContour(Contour):
    """A contour holding an aggregation of other contours."""

    def __init__(self, contours, operation):
        super().__init__()
        self._member_contours = contours
        self._operation = operation
        self._contour = operation([c._contour for c in self._member_contours])
        self._contour_times = contours[0]._contour_times
        self._is_real_time = np.any([c.is_real_time for c in self._member_contours])

    def at(self, time):

        if self.is_real_time:

            # retrieve the at value of every member
            values = [[c.at(time)] for c in self._member_contours]
            values = np.array(values)
            # values = np.nan_to_num(values, nan=0.5)

            # aggregate
            res = self._operation(values)

            if np.isnan(res[0]):
                print(self._operation)
                raise Exception

            return res[0]
        else:
            return super().at(time)


class RandomContour(Contour):
    """A randomly initialized contour."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tu.Tune, min: float = 0, max: float = 1) -> None:
        """Compute a random contour following a uniform distribution in the specified range, by default between 0 and 1.

        :param midi: the input tune.
        :param extremes: the upper and lower bound for the random contour. If None, the range will be (0, 1).
        """
        super().calculate(midi)

        size = len(midi.pitches)
        r_min = min
        r_max = max
        self._contour = np.clip(
            np.random.normal(loc=0.5, scale=0.5 / 3, size=size),
            a_min=r_min,
            a_max=r_max,
        )


class PhraseContour(Contour):
    """A contour representing phrase arcs."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tu.Tune,
        accelerando=0.5,
        ritardando=1,
        turn=0.3,
        last=0.2,
        power=2,
        phrase_length=2,
        shift=None,
        mode="contour",
        kind="arch",
    ) -> None:
        """Compute a phrasing contour.

        :param midi: the input tune.
        """
        assert mode in ["contour", "ratio"]
        assert kind in ["arch", "gesture"]

        super().calculate(midi)

        if shift is None:
            shift = -midi._first_bar_length

        bar_length = midi.time_signatures[0].eighths_per_bar.eighth_duration
        phrase_eighths = bar_length * phrase_length
        # consider note onset + half of duration as phrase position
        # anders says it works better
        note_durations = np.array([d.eighth_duration for d in midi.durations])
        note_positions = self._contour_times + note_durations / 2
        phrase_position = ((note_positions - shift) % phrase_eighths) / phrase_eighths

        if kind == "arch":
            acc = 0.1 * accelerando * (1 - (phrase_position / turn)) ** power
            rit = 0.2 * ritardando * ((phrase_position - turn) / (1 - turn)) ** power
            perc = np.maximum(np.minimum(1, np.floor(phrase_position / turn)), 0)
            last_perc = np.maximum(
                np.minimum(
                    1,
                    np.ceil(
                        phrase_position
                        - 1
                        + 1 / bar_length
                        + 2 / le.MINIMUM_QUARTER_DIVISION,
                    ),
                ),
                0,
            )
            tmp = (1 - last_perc + last * last_perc) * ((1 - perc) * acc + perc * rit)

            # no need to account for another phrase
            last_phrase_index = np.argwhere(phrase_position == 0)
            if len(last_phrase_index) != 0:
                last_phrase_index = last_phrase_index[-1][0]
                tmp[last_phrase_index:] = (1 - perc[last_phrase_index:]) * acc[
                    last_phrase_index:
                ] + perc[last_phrase_index:] * rit[last_phrase_index:]

            tmp += 1
        elif kind == "gesture":
            k = 0.229402
            perc = np.maximum(np.minimum(1, np.floor(phrase_position / turn)), 0)
            phrase_position = (1 - perc) * (
                phrase_position * (0.5 - k) / turn + k
            ) + perc * ((phrase_position - turn) * (1 - k - 0.5) / (1 - turn) + 0.5)
            tmp = 1 / (16 * (phrase_position - 1) ** 2 * phrase_position**2)

        if mode == "contour":
            self._contour = 1 / tmp
        elif mode == "ratio":
            self._contour = tmp


class IntensityContour(Contour):
    """A contour given by the weighted sum of O'Canainn components."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tu.Tune,
        weights: list = None,
        savgol: bool = True,
        shift: bool = False,
        scale: bool = False,
    ) -> None:
        """Compute the contour as the weighted sum of O'Canainn component.
        An optional random component can be added.

        :param midi: the input tune.
        :param weights: the weights for the components, respectively frequency score, beat score, ambitus score, leap score and length score.
        :param savgol: whether or not to apply a final savgol filtering step (recommended).
        :param shift: whether or not to apply a final shifting step to bring the mean of the array close to 0.5.
        """
        super().calculate(midi)

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
        self, midi: tu.Tune
    ) -> tuple[np.array, np.array, np.array, np.array, np.array]:
        """Computes the individual components for the ocanainn score:

        * frequency score;
        * beat score;
        * ambitus score;
        * leap score;
        * length score.

        :param midi: the input tune used to compute the individual scores.

        :return: the frequency score, the beat score, the ambitus score, the leap score and the length score.
        """
        pitches = midi.pitches
        durations = midi.durations

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
        indexes = np.where(
            self._contour_times
            % (
                # TODO make this keep track of time signatures
                midi.time_signatures[0].eighths_per_bar.eighth_duration
                / midi.time_signatures[0].beat_count
            )
            == 0
        )
        beats = -np.ones(notes.shape)
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
        values, counts = np.unique(durations, return_counts=True)
        index = np.argmax(counts)
        val = values[index]
        length_score = (durations > val).astype(float)

        return frequency_score, beat_score, ambitus_score, leap_score, length_score


class PitchContour(Contour):
    """A contour holding the pitch of notes in the tune."""

    def __init__(self):
        super().__init__()

    def calculate(
        self,
        midi: tu.Tune,
        savgol: bool = True,
        shift: bool = True,
        scale: bool = True,
    ) -> None:

        super().calculate(midi)

        self._contour = midi.pitches

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
        midi: tu.Tune,
        mean: list = [1],
        std: list = [0],
        std_scale: float = 1,
        normalize: bool = False,
        period: float = 1,
    ) -> None:
        """Create the contour by repeating the input weights over the specified period.
        If standard deviatons are specified, the resulting patter is sampled from each distribution at each loaction.

        :param mean: the pattern to repeat.
        :param std: the std of the pattern to repeat, for every item.
        :param period: the length of the pattern, in bars.
        """
        super().calculate(midi)

        if std is None:
            std = np.zeros(len(mean))
        assert len(mean) == len(std)

        self._is_real_time = True

        self._mean = np.array(mean).astype(float)
        self._std = np.array(std).astype(float)
        self._std_scale = std_scale
        self._normalize = normalize
        self._pattern_size = len(self._mean)

        # obtain time pedios
        self._time_period = midi.time_signatures[
            0
        ].eighths_per_bar.eighth_duration * float(period)
        # position in time period
        bar_position = self._contour_times / self._time_period

        # obtain indexes (without module to check jumps)
        pattern_indexes = (self._pattern_size * bar_position).astype(int)

        # obtain jumps in pattern
        diff = np.diff(pattern_indexes)
        index_diff = np.argwhere(diff > 1)

        # bring pattern back to size
        pattern_indexes %= self._pattern_size
        pattern_means = self._mean[pattern_indexes].astype(float)
        pattern_stds = self._std[pattern_indexes].astype(float)

        # add missing indexes together only if
        # normalising, otherwise use whatever value
        # was already there
        if normalize:
            for index in index_diff:
                source_index = pattern_indexes[index].item()
                add_indexes = (
                    np.arange(source_index, source_index + diff[index].item())
                    % self._pattern_size
                )
                pattern_means[index] = np.mean(self._mean[add_indexes])
                pattern_stds[index] = np.mean(self._std[add_indexes])

        pattern = np.random.normal(
            loc=pattern_means,
            scale=self._std_scale * pattern_stds,
            size=len(pattern_means),
        )

        if normalize:
            bars = self._contour_times // self._time_period
            durations = midi.float_durations

            for i in np.unique(bars):
                indexes = np.argwhere(bars == i)
                bar_durations = durations[indexes]
                pattern[indexes] /= np.multiply(pattern[indexes], bar_durations).sum()
                pattern[indexes] *= bar_durations.sum()

        self._contour = pattern

    def at(self, time):
        if self._normalize:
            value = super().at(time)
        else:
            position = time.eighth_duration / self._time_period
            index = ((len(self._mean) * position) % len(self._mean)).astype(int)
            value = np.random.normal(
                loc=self._mean[index],
                scale=self._std_scale * self._std[index],
                size=1,
            )[0]
        if np.isnan(value):
            raise Exception
        return value


def multiply(contours: list[Contour] = []) -> Contour:
    """Returns a new contour that holds the product of the input contours.

    :param contours: the contours to multiply.

    :return: a new contour holding the product of the input contours.
    """

    def mult(contours):
        result = np.ones(len(contours[0]))
        for c in contours:
            result = np.multiply(result, c)

        return result

    new_contour = CompositeContour(contours, lambda cnt_list: mult(cnt_list))

    return new_contour


def weighted_sum(
    contours: list[Contour] = [], weights: list = [], normalize: bool = True
) -> Contour:
    """Returns a new contour that holds the weighted sum of the input contours.

    :param contours: the contours to add.
    :param weights: the weight for each contour.
    :param normalize: have the weights sum to 1

    :return: a new contour holding the weighted sum of the input contours.
    """
    assert len(contours) == len(weights)

    size = len(contours)
    weights = np.array(weights).astype(float)
    if weights is None:
        weights = np.ones((size, 1))
    else:
        if weights.shape != (size, 1):
            weights = weights.reshape(size, 1)
        indexes = np.argwhere(weights < 0)
        weights = abs(weights)

    if normalize:
        weights /= weights.sum()

    def wsum(contours, weights):
        result = np.zeros(len(contours[0]))

        stacked_components = np.stack(contours)

        # invert negative ones
        stacked_components[indexes] *= -1
        stacked_components[indexes] += 1

        # weight them
        stacked_components = np.multiply(stacked_components, weights)
        # sum them
        result = stacked_components.sum(axis=0)

        return result

    new_contour = CompositeContour(contours, lambda cnt_list: wsum(cnt_list, weights))
    return new_contour


def linear_transform(contours: Contour = None, a: float = 1, b: float = 0) -> Contour:
    """Apply a linear transformation of the input contour f(x)= ax + b.

    :param contour: the input contour.
    :param a: the slope.
    :param b: the intercept.

    :return: the linear transformation of the input contour.
    """
    assert len(contours) == 1

    def lin(x, a, b):
        return a * x + b

    new_contour = CompositeContour(contours, lambda cnt_list: lin(cnt_list[0], a, b))

    return new_contour


def clamp(contours: Contour = None, low: float = 0, high: float = 1) -> Contour:
    """Clamp the contour in the given range.

    :param contour: the input contour.
    :param low: the lower limit.
    :param high: the higher limit.

    :return: the clamped input contour.
    """
    assert len(contours) == 1
    new_contour = CompositeContour(
        contours, lambda cnt_list: np.clip(cnt_list[0], a_min=low, a_max=high)
    )

    return new_contour


def shift(contours: list[Contour] = None, offset: int = -1) -> Contour:
    """Shift the contour by offset.

    :param contour: the input contour.
    :param offset: the offset of the contour, in note indexes.

    :return: the shifted input contour.
    """
    assert len(contours) == 1

    new_contour = CompositeContour(
        contours, lambda cnt_list: np.roll(cnt_list[0], offset)
    )
    return new_contour


def to_mean(contours: list[Contour] = None, mean: float = 0.5) -> Contour:
    """Shift the contour so that it has a specific mean.

    :param contour: the input contour.
    :param mean: the desired mean.

    :return: the shifted input contour.
    """
    assert len(contours) == 1
    new_contour = CompositeContour(
        contours, lambda cnt_list: cnt_list[0] - cnt_list[0].mean() + mean
    )
    return new_contour


def power(contours: list[Contour] = None, exp: float = 1) -> Contour:
    """Elevate the contour to the specified power.

    :param contour: the input contour.
    :param exp: the exponent.

    :return: the modified input contour.
    """
    assert len(contours) == 1
    new_contour = CompositeContour(contours, lambda cnt_list: cnt_list[0] ** exp)
    return new_contour


def smooth(contours: list[Contour] = None, window: float = 15) -> Contour:
    """Elevate the contour to the specified power.

    :param contour: the input contour.
    :param exp: the exponent.

    :return: the modified input contour.
    """
    assert len(contours) == 1

    def smth(x, window):
        x = np.pad(x, (window, window), "mean")
        x = savgol_filter(x, window, 3)
        x = x[window:-window]
        return x

    new_contour = CompositeContour(contours, lambda cnt_list: smth(cnt_list[0], window))

    return new_contour


def scale(contours: list[Contour] = None, min: float = 0, max: float = 1) -> Contour:
    """Scale a contour to cover a specific interval.

    :param contour: the input contour.
    :param min: the minimum value.
    :param max: the maximum value.

    :return: the modified input contour.
    """
    assert len(contours) == 1

    def scl(x, a, b, min_x, max_x):
        x -= min_x
        x /= max_x - min_x
        return a + (b - a) * x

    min_x = np.min(contours[0].values)
    max_x = np.max(contours[0].values)

    new_contour = CompositeContour(
        contours,
        lambda cnt_list: scl(cnt_list[0], min, max, min_x, max_x),
    )

    return new_contour


def create_contour(
    tune: tu.Tune, contour_program: dict, key=None, parent=None
) -> Contour:
    """Programmatically create a contour given its definition.

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
        "to_mean": to_mean,
        "power": power,
        "clamp": clamp,
        "scale": scale,
        "smooth": smooth,
    }

    if key is not None:
        key = key.split("#")[0]

    # check
    if key is None:
        c = list(contour_program.keys())
        if len(c) != 1:
            raise InvalidRecipeError(
                f"Only one contour can be provided. Make sure that 'recipe' in contour {parent} only has one item in the configuration file."
            )
        c = c[0]
        return create_contour(tune, contour_program[c], key=c, parent=parent)

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
                create_contour(
                    tune, contour_program["contours"][c], key=c, parent=parent
                )
            )

        program = contour_program.copy()
        program["contours"] = all_contours
        return operation_dict[key](**program)

    else:
        raise InvalidRecipeError(
            f"Recipe argument {key} is invalid. Check your configuration file."
        )
