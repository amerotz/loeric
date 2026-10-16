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

import numpy as np

import loeric.core.element as le
import loeric.core.tune as tu
from loeric.core.contours.base import NotewiseContour, NotewiseContourConfig


class PhraseContourConfig(NotewiseContourConfig):
    mode: str
    turn: float = 0.3
    phrase_length: float = 2
    shift: None | int = None


class GesturePhraseContourConfig(PhraseContourConfig):
    pass


class ArchPhraseContourConfig(PhraseContourConfig):

    accelerando: float = 0.5
    ritardando: float = 1
    last: float = 0.2
    power: float = 2


class PhraseContour(NotewiseContour):
    """A contour representing phrases."""

    config_class = PhraseContourConfig

    def __init__(
        self,
        turn=0.3,
        phrase_length=2,
        shift=None,
        mode="contour",
    ):
        assert mode in ["contour", "ratio"]

        super().__init__()

        self._phrase_length = phrase_length
        self._shift = shift
        self._turn = turn
        self._mode = mode

    def calculate(
        self,
        tune: tu.Tune,
    ) -> None:
        """Compute a phrasing contour.

        :param tune: the input tune.
        """
        super().calculate(tune)

        if self._shift is None:
            self._shift = -tune._first_bar_length

        time_signatures = tune.time_signatures
        note_durations = tune.float_durations

        phrase_position = []
        bar_length = []
        # iterate over time signatures
        for i in range(len(time_signatures)):
            ts_1 = time_signatures[i]
            t1 = float(ts_1.time)

            if i < len(time_signatures) - 1:
                t2 = float(time_signatures[i + 1].time)
            else:
                t2 = np.inf

            b_len = ts_1.eighths_per_bar.eighth_duration
            phrase_eighths = b_len * self._phrase_length

            indexes = np.argwhere(
                (self._contour_times >= t1) & (self._contour_times < t2)
            )

            times = self._contour_times[indexes]
            durations = note_durations[indexes]
            # consider note onset + half of duration as phrase position
            # anders says it works better
            note_positions = times + durations / 2

            phrase_position.append(
                (
                    ((note_positions - self._shift) % phrase_eighths) / phrase_eighths
                ).flatten()
            )
            bar_length.append(np.repeat(b_len, len(indexes)).flatten())

        phrase_position = np.concat(phrase_position)
        bar_length = np.concat(bar_length)

        # actual phrase calculation
        tmp = self._calculate_phrases(phrase_position, bar_length)

        if self._mode == "contour":
            self._contour = 1 / tmp
        elif self._mode == "ratio":
            self._contour = tmp


class GesturePhraseContour(PhraseContour):
    """A contour representing phrase arcs."""

    config_class = GesturePhraseContourConfig

    def __init__(
        self,
        turn=0.3,
        phrase_length=2,
        shift=None,
        mode="contour",
    ):
        assert mode in ["contour", "ratio"]

        super().__init__()

        self._phrase_length = phrase_length
        self._shift = shift
        self._turn = turn
        self._mode = mode

    def _calculate_phrases(self, phrase_position, bar_length):
        k = 0.229402
        perc = np.maximum(np.minimum(1, np.floor(phrase_position / self._turn)), 0)
        phrase_position = (1 - perc) * (
            phrase_position * (0.5 - k) / self._turn + k
        ) + perc * (
            (phrase_position - self._turn) * (1 - k - 0.5) / (1 - self._turn) + 0.5
        )
        tmp = 1 / (16 * (phrase_position - 1) ** 2 * phrase_position**2)
        return tmp


class ArchPhraseContour(PhraseContour):
    """A contour representing phrase arcs."""

    config_class = ArchPhraseContourConfig

    def __init__(
        self,
        accelerando=0.5,
        ritardando=1,
        turn=0.3,
        last=0.2,
        power=2,
        phrase_length=2,
        shift=None,
        mode="contour",
    ):
        assert mode in ["contour", "ratio"]

        super().__init__()

        self._phrase_length = phrase_length
        self._mode = mode
        self._shift = shift
        self._turn = turn

        self._accelerando = accelerando
        self._ritardando = ritardando
        self._last = last
        self._power = power

    def _calculate_phrases(self, phrase_position, bar_length):
        acc = (
            0.1
            * self._accelerando
            * (1 - (phrase_position / self._turn)) ** self._power
        )
        rit = (
            0.2
            * self._ritardando
            * ((phrase_position - self._turn) / (1 - self._turn)) ** self._power
        )
        perc = np.maximum(np.minimum(1, np.floor(phrase_position / self._turn)), 0)
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
        tmp = (1 - last_perc + self._last * last_perc) * ((1 - perc) * acc + perc * rit)

        # no need to account for another phrase
        last_phrase_index = np.argwhere(phrase_position == 0)
        if len(last_phrase_index) != 0:
            last_phrase_index = last_phrase_index[-1][0]
            tmp[last_phrase_index:] = (1 - perc[last_phrase_index:]) * acc[
                last_phrase_index:
            ] + perc[last_phrase_index:] * rit[last_phrase_index:]

        tmp += 1
        return tmp
