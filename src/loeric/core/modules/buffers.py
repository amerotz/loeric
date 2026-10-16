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

from typing import Literal

from pydantic import field_validator

import loeric.core.element as le
import loeric.core.modules.base as lmb
import loeric.core.paths as lp


class DelayBufferModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`DelayBufferModule`.

    :param size: lookahead buffer size in eighths. Must be positive.
    """

    size: float
    type: Literal["delay_buffer"]

    @field_validator("size")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"size must be positive, got {v}")
        return v


class HistoryBufferModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`HistoryBufferModule`.

    :param size: lookback buffer size in eighths. Must be positive.
    """

    size: float
    type: Literal["history_buffer"]

    @field_validator("size")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"size must be positive, got {v}")
        return v


@lp.expose("_lookback_size", "size")
class HistoryBufferModule(lmb.LOERICModule):

    config_class = HistoryBufferModuleConfig

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


@lp.expose("_lookahead_size", "size")
class DelayBufferModule(lmb.LOERICModule):

    config_class = DelayBufferModuleConfig

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
