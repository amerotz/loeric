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
import loeric.core.paths as lp


class TransposeConfig(lmb.ModuleConfig):
    """Config for :class:`TransposeModule`.

    :param steps: number of semitones to transpose (may be fractional).
    """

    steps: float = 0.0


@lp.expose("_steps", "steps")
class TransposeModule(lmb.LOERICModule):

    config_class = TransposeConfig

    def __init__(self, steps: float, **kwargs):
        super().__init__(**kwargs)

        self._steps = steps
        self._name = "transpose"

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Transpose notes.

        :param element: the element to process.
        """
        if (
            isinstance(element, le.Note)
            or isinstance(element, le.Chord)
            or isinstance(element, le.KeySignature)
        ):
            element.transpose(self._steps)
        return [element]
