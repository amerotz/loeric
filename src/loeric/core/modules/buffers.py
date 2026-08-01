from pydantic import field_validator

import loeric.core.element as le
import loeric.core.modules.base as lmb


class DelayBufferConfig(lmb.ModuleConfig):
    """Config for :class:`DelayBufferModule`.

    :param size: lookahead buffer size in eighths. Must be positive.
    """

    size: float

    @field_validator("size")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"size must be positive, got {v}")
        return v


class HistoryBufferConfig(lmb.ModuleConfig):
    """Config for :class:`HistoryBufferModule`.

    :param size: lookback buffer size in eighths. Must be positive.
    """

    size: float

    @field_validator("size")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"size must be positive, got {v}")
        return v


class HistoryBufferModule(lmb.LOERICModule):

    config_class = HistoryBufferConfig

    def __init__(self, size: float, **kwargs):

        super().__init__(**kwargs)

        self._name = "buffer"
        assert size > 0, "Buffer size cannot be 0 or negative"
        self._lookahead_size = 0
        self._lookback_size = size
        self._buffer = []

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):

        current_time = element.time

        # update buffer
        self._buffer.append(element)

        self._buffer = [
            el for el in self._buffer if current_time - el.time < self._lookback_size
        ]

        return [element]


class DelayBufferModule(lmb.LOERICModule):

    config_class = DelayBufferConfig

    def __init__(self, size: float, **kwargs):

        super().__init__(**kwargs)

        self._name = "buffer"
        assert size > 0, "Buffer size cannot be 0 or negative"
        self._lookahead_size = size
        self._lookback_size = 0
        self._buffer = []

    def _process(self, element, window=None):

        current_time = element.time
        self._buffer.append(element)

        ready = []
        pending = []
        for el in self._buffer:
            if current_time - el.time >= self._lookahead_size:
                ready.append(el)
            else:
                pending.append(el)
        self._buffer = pending

        if not ready:
            return [le.NullEvent(time=current_time)]
        return ready
