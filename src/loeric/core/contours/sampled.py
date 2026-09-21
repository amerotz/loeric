import numpy as np

import loeric.core.tune as tu
from loeric.core.contours.base import Contour


class RandomContour(Contour):
    """A randomly initialized contour."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tu.Tune, min: float = 0, max: float = 1) -> None:
        """Compute a random contour following a uniform distribution.

        Default range is between 0 and 1.

        :param midi: the input tune.
        :param extremes: the upper and lower bound for the random contour.
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

        If standard deviatons are specified, the resulting pattern is sampled
        from each distribution at each loaction.

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

        # obtain time periods
        # TODO multiple time signatures
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

    def _at(self, time):
        if self._normalize:
            value, index = super()._at(time)
        else:
            position = time.eighth_duration / self._time_period
            index = int((len(self._mean) * position) % len(self._mean))
            value = np.random.normal(
                loc=self._mean[index],
                scale=self._std_scale * self._std[index],
                size=1,
            )[0]

        if np.isnan(value):
            raise Exception
        return value, index
