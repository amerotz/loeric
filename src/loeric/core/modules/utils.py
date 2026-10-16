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
from typing import Any, Literal

from pydantic import BaseModel, field_validator

import loeric.core.element as le
import loeric.core.modules as lm
import loeric.core.modules.base as lmb

logger = logging.getLogger(__name__)


class TaggerModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`TaggerModule`. No additional fields beyond the base."""

    type: Literal["tagger"]


class LoggerModuleConfig(lmb.BaseModuleConfig):
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
    type: Literal["logger"]


class TaggerModule(lmb.LOERICModule):

    config_class = TaggerModuleConfig

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

    config_class = LoggerModuleConfig

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
