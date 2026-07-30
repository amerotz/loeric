import copy

import loeric.core.element as le
import loeric.core.module.base as lmb
import loeric.core.paths as lp


class TimingConfig(lmb.ModuleConfig):
    """Config for :class:`TimingModule`.

    :param bind: contour name controlling tempo variation.
    :param pattern: contour name for the timing pattern multiplier.
    :param qpm_amount: maximum QPM deviation.
    :param only_increase: if ``True``, tempo can only be increased.
    """

    bind: str
    pattern: str
    qpm_amount: float
    only_increase: bool = False


@lp.expose("_contour", "bind")
@lp.expose("_pattern", "pattern")
@lp.expose("_qpm_amount", "qpm_amount")
@lp.expose("_only_increase", "only_increase")
class TimingModule(lmb.LOERICModule):

    config_class = TimingConfig
    _contour: str
    _pattern: str
    _qpm_amount: float
    _only_increase: bool

    def __init__(
        self, bind: str, pattern: str, qpm_amount: float, only_increase: bool, **kwargs
    ):
        super().__init__(**kwargs)

        self._name = "timing"
        self._contour = bind
        self._pattern = pattern
        self._qpm_amount = qpm_amount
        self._only_increase = only_increase

        self._internal_offset = 0
        self._last_computation_time = le.TimeDelta(0)
        self._offset_snapshot = 0
        self._is_online = True

        self._first_tempo = None
        self._user_tempo_to_original_ratio = 1

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply timing.

        :param element: the element to process.
        """
        if isinstance(element, le.UserTempo):
            self._user_tempo_to_original_ratio = element.qpm / self._first_tempo.qpm
        elif isinstance(element, le.Tempo):
            if self._first_tempo is None:
                self._first_tempo = element

        elif not isinstance(element, le.NullEvent) and element.is_performable:
            element = self._process_element(element)

        ret_val = [element]
        # always update tempo
        if self._tempo is not None:
            qpm = self._process_tempo()
            ret_val.insert(0, le.Tempo(qpm=qpm, time=element.time))
        return ret_val

    def _process_element(
        self,
        element: le.LOERICElement,
    ):
        current_time = copy.deepcopy(element.time)

        # all simultaneous notes share same offset
        update_offset = (
            element.is_performable and self._last_computation_time != current_time
        )

        if update_offset:
            self._last_computation_time = current_time
            self._offset_snapshot = self._internal_offset

        # keep original duration
        old_duration = element.duration.eighth_duration
        new_duration = old_duration * self._contour_values[self._pattern]

        # apply timing
        element.duration = new_duration

        # apply offset
        element.time -= self._offset_snapshot

        # only integrate once per score-time
        if update_offset:
            self._internal_offset += old_duration - new_duration

        return element

    def _process_tempo(self):

        bpm = self._tempo.qpm * self._user_tempo_to_original_ratio
        value = 2 * self.qpm_amount * (self._contour_values[self._contour] - 0.5)

        calculated_tempo = bpm + value

        if self._only_increase:
            tempo = max(self._tempo.qpm, calculated_tempo)
        else:
            tempo = calculated_tempo

        return tempo
