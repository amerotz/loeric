import numpy as np

import loeric.core.element as le
import loeric.core.tune as tu
from loeric.core.contours.base import NotewiseContour, NotewiseContourConfig


class PhraseContourConfig(NotewiseContourConfig):

    accelerando: float = 0.5
    ritardando: float = 1
    turn: float = 0.3
    last: float = 0.2
    power: float = 2
    phrase_length: float = 2
    shift: None | int = None
    mode: str = "contour"
    kind: str = "arch"


class PhraseContour(NotewiseContour):
    """A contour representing phrase arcs."""

    config_class = PhraseContourConfig

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
        kind="arch",
    ):
        assert mode in ["contour", "ratio"]
        assert kind in ["arch", "gesture"]

        super().__init__()

        self._phrase_length = phrase_length
        self._accelerando = accelerando
        self._ritardando = ritardando
        self._turn = turn
        self._last = last
        self._power = power
        self._shift = shift
        self._mode = mode
        self._kind = kind

    def calculate(
        self,
        tune: tu.Tune,
    ) -> None:
        """Compute a phrasing contour.

        :param tune: the input tune.
        """
        super().calculate(tune)

        if self._shift is None:
            shift = -tune._first_bar_length

        time_signatures = tune.time_signatures
        note_durations = tune.float_durations

        phrase_position = []
        # iterate over time signatures
        for i in range(len(time_signatures)):
            ts_1 = time_signatures[i]
            t1 = float(ts_1.time)

            if i < len(time_signatures) - 1:
                t2 = float(time_signatures[i + 1].time)
            else:
                t2 = np.inf

            bar_length = ts_1.eighths_per_bar.eighth_duration
            phrase_eighths = bar_length * self._phrase_length

            indexes = np.argwhere(
                (self._contour_times >= t1) & (self._contour_times < t2)
            )

            times = self._contour_times[indexes]
            durations = note_durations[indexes]
            # consider note onset + half of duration as phrase position
            # anders says it works better
            note_positions = times + durations / 2

            phrase_position.append(
                (((note_positions - shift) % phrase_eighths) / phrase_eighths).flatten()
            )

        phrase_position = np.concat(phrase_position)

        if self._kind == "arch":
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
            tmp = (1 - last_perc + self._last * last_perc) * (
                (1 - perc) * acc + perc * rit
            )

            # no need to account for another phrase
            last_phrase_index = np.argwhere(phrase_position == 0)
            if len(last_phrase_index) != 0:
                last_phrase_index = last_phrase_index[-1][0]
                tmp[last_phrase_index:] = (1 - perc[last_phrase_index:]) * acc[
                    last_phrase_index:
                ] + perc[last_phrase_index:] * rit[last_phrase_index:]

            tmp += 1
        elif self._kind == "gesture":
            k = 0.229402
            perc = np.maximum(np.minimum(1, np.floor(phrase_position / self._turn)), 0)
            phrase_position = (1 - perc) * (
                phrase_position * (0.5 - k) / self._turn + k
            ) + perc * (
                (phrase_position - self._turn) * (1 - k - 0.5) / (1 - self._turn) + 0.5
            )
            tmp = 1 / (16 * (phrase_position - 1) ** 2 * phrase_position**2)

        if self._mode == "contour":
            self._contour = 1 / tmp
        elif self._mode == "ratio":
            self._contour = tmp
