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

import loeric.core.element as le
import loeric.core.modules.base as lmb


class LegatoConfig(lmb.ModuleConfig):
    """Config for :class:`LegatoModule`.

    :param bind: contour name controlling legato amount.
    :param min: minimum legato multiplier.
    :param max: maximum legato multiplier.
    """

    bind: str
    min: float
    max: float


class LegatoModule(lmb.LOERICModule):

    config_class = LegatoConfig

    def __init__(self, min: float, max: float, bind: str, **kwargs):
        super().__init__(**kwargs)

        self._name = "legato"
        self._legato_amount = max - min
        self._min_legato = min
        self._contour = bind
        self._is_online = True

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Apply legato.

        :param element: the element to process.
        """
        if isinstance(element, le.Note):
            element.duration *= (
                self._min_legato
                + self._legato_amount * self._contour_values[self._contour]
            )
        return [element]
