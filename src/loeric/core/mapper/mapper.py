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

"""The Mapper is responsible for the routing and weighting of signals."""

import logging

import loeric.core.element as le
import loeric.core.mapper.engines.matrix as lme
import loeric.core.mapper.parser as lmP

logger = logging.getLogger(__name__)


class Mapper:

    def __init__(self, config):

        self._parser = lmP.LOERICMapperParser()
        self._engine = lme.MatrixEngine(
            sources=config["sources"], targets=config["targets"]
        )

        # parse rules
        for rule in config["rules"]:
            obj = self._parser.parse(rule)
            # process in the engine
            self._engine.process(obj)

    def reset(self):
        self._engine.reset()

    def __setitem__(self, key: str, value: float) -> None:
        """Set the control named ``key`` to ``value``."""
        self._engine[key] = value

    def __getitem__(self, key: str) -> float:
        """Get the value of control named ``key``."""
        return self._engine[key]

    def update(self):
        """Update output values given inputs and the specified routing."""
        self._engine.update()

    def set(self, inputs: list[le.LOERICElement]):
        """Set input values."""
        self._engine.set(inputs)

    def get(self, as_array=False):
        """Get output values."""
        return self._engine.get(as_array=as_array)
