import numpy as np

import loeric.core.tune as tu
from loeric.core.contours.base import Contour


class BarLengthContour(Contour):
    """A contour holding the length of each note in the tune."""

    def __init__(self):
        super().__init__()

    def calculate(self, midi: tu.Tune) -> None:
        """Contains the length of the bar each note occupies.

        :param midi: the input tune object.
        """
        super().calculate(midi)

        self._contour = np.empty(self._contour_times.shape)
        # iterate over time signatures
        for i in range(len(midi.time_signatures)):
            ts_1 = midi.time_signatures[i]
            t1 = float(ts_1.time)

            if i < len(midi.time_signatures) - 1:
                t2 = float(midi.time_signatures[i + 1].time)
            else:
                t2 = np.inf

            bar_length = ts_1.eighths_per_bar.eighth_duration

            indexes = np.argwhere(
                (self._contour_times >= t1) & (self._contour_times < t2)
            )

            self._contour[indexes] = bar_length
