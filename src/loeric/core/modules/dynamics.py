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

import loeric.core.element as le
import loeric.core.modules.base as lmb
import loeric.core.paths as lp


class DynamicsModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`DynamicsModule`.

    :param bind: contour name controlling velocity.
    :param pattern: contour name for the velocity pattern multiplier.
    """

    bind: str
    pattern: str = None
    type: Literal["dynamics"]


@lp.expose("_contour", "bind")
@lp.expose("_pattern", "pattern")
class DynamicsModule(lmb.LOERICModule):

    config_class = DynamicsModuleConfig

    def __init__(self, bind: str, pattern: str, **kwargs):
        super().__init__(**kwargs)

        self._contour = bind
        self._pattern = pattern
        self._name = "dynamics"
        self._is_online = True
        self._required_contours = {bind, pattern}

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply dynamics.

        :param element: the element to process.
        """
        if isinstance(element, le.Note):
            element.velocity = self._contour_values[self._contour]
            if self._pattern is not None:
                element.velocity *= self._contour_values[self._pattern]
        return [element]
