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


class ChainModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`ChainModule`.

    :param modules: a chain of module configurations.
    """

    modules: dict[str, Any]
    type: Literal["chain"]


class ChainModule(lmb.LOERICModule):

    config_class = ChainModuleConfig

    def __init__(self, modules: dict, **kwargs):
        super().__init__(**kwargs)

        self._name = "chain"

        self._modules = []
        self._is_online = False

        for m in modules:
            module = lm.create_module(m, **modules[m])
            self._is_online = self._is_online or module.is_online
            self._required_contours.update(module.required_contours)
            self._modules.append(module)

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Execute the module if the condition is met.

        :param element: the element to process.
        """

        # run it through the modules
        to_be_processed_by_module = [element]

        for module in self._modules:
            spawned_elements = []
            for e in to_be_processed_by_module:
                module_output = module(e, window=window)
                spawned_elements.extend(module_output)

            # next step will process eveything spawned
            # at current time
            to_be_processed_by_module = spawned_elements

        return to_be_processed_by_module
