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
import logging
from typing import Any

from pydantic import BaseModel, field_validator

import loeric.core.element as le
import loeric.core.module.base as lmb

logger = logging.getLogger(__name__)


class ConditionConfig(BaseModel):
    """Config for a :class:`LOERICCondition`.

    :param attribute: element attribute to test.
    :param operation: comparison operator string.
    :param value: value to compare against.
    """

    attribute: str
    operation: str
    value: Any

    @field_validator("operation")
    @classmethod
    def valid_operator(cls, v: str) -> str:
        allowed = {"==", "<", ">", ">=", "<=", "!="}
        if v not in allowed:
            raise ValueError(f"Unknown operator '{v}'. Allowed: {allowed}")
        return v


class ConditionalConfig(lmb.ModuleConfig):
    """Config for :class:`ConditionalModule`.

    :param condition: the condition to evaluate.
    :param module: a single-key dict mapping a module name to its config.
    """

    condition: ConditionConfig
    module: dict[str, Any]

    @field_validator("module")
    @classmethod
    def single_module(cls, v: dict) -> dict:
        if len(v) != 1:
            raise ValueError(f"'module' must contain exactly one entry, got {len(v)}")
        return v


class TaggerConfig(lmb.ModuleConfig):
    """Config for :class:`TaggerModule`. No additional fields beyond the base."""

    pass


class LoggerConfig(lmb.ModuleConfig):
    """Config for :class:`LoggerModule`.

    :param notes: log note events.
    :param chords: log chord events.
    :param time_signatures: log time signature events.
    :param key_signatures: log key signature events.
    :param tempos: log tempo events.
    """

    notes: bool = False
    chords: bool = False
    time_signatures: bool = False
    key_signatures: bool = False
    tempos: bool = False


class LOERICCondition:

    def __init__(self, **kwargs):

        self._operation_dict = {
            "==": lambda x, y: x == y,
            "<": lambda x, y: x < y,
            ">": lambda x, y: x > y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "!=": lambda x, y: x != y,
        }

        self._attribute = kwargs["attribute"]
        self._value = kwargs["value"]

        assert (
            kwargs["operation"] in self._operation_dict
        ), f"Unknown operator {kwargs["operation"]}"
        self._operation = self._operation_dict[kwargs["operation"]]

    def eval(self, element):

        if hasattr(element, self._attribute):
            return self._operation(getattr(element, self._attribute), self._value)

        else:
            logger.warning(f"{element} has no attribute {self._attribute}.")
            return False

    def __call__(self, element):
        return self.eval(element)


class ConditionalModule(lmb.LOERICModule):

    config_class = ConditionalConfig

    def __init__(self, condition: dict, module: dict, **kwargs):
        super().__init__(**kwargs)

        self._name = "conditional"

        name = list(module.keys())[0]
        self._module = lmb.LOERICModule.create_module(name, **module[name])
        self._condition = LOERICCondition(**condition)

        self._is_online = self._module.is_online

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Execute the module if the condition is met.

        :param element: the element to process.
        """
        if not element.is_performable:
            val = self._module(element, window)

        if self._condition(element):
            if element.is_performable:
                val = self._module(element, window)
            return val
        else:
            return [element]


class TaggerModule(lmb.LOERICModule):

    config_class = TaggerConfig

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._name = "tagger"

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Tags notes.

        :param element: the element to process.
        """
        return [element]


class LoggerModule(lmb.LOERICModule):

    config_class = LoggerConfig

    def __init__(
        self,
        chords: bool,
        notes: bool,
        time_signatures: bool,
        key_signatures: bool,
        tempos: bool,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._do_chords = chords
        self._do_notes = notes
        self._do_time_s = time_signatures
        self._do_key_s = key_signatures
        self._do_tempo = tempos

        self._name = "logger"

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):

        if self._do_chords and isinstance(element, le.Chord):
            if element.is_user:
                logger.info(f"Forcing chord {element}")
            else:
                logger.info(f"Playing chord {element}")

        elif self._do_notes and isinstance(element, le.Note):
            logger.info(element)
        elif self._do_time_s and isinstance(element, le.TimeSignature):
            logger.info(element)
        elif self._do_key_s and isinstance(element, le.KeySignature):
            logger.info(element)
        elif self._do_tempo and isinstance(element, le.Tempo):
            logger.info(element)

        return [element]
