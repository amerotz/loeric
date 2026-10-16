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

import pydantic as pdt

import loeric.core.element as le
import loeric.core.mapper.engines.matrix as lme
import loeric.core.mapper.parser as lmp
import loeric.core.paths as lp

logger = logging.getLogger(__name__)


class MapperConfig(pdt.BaseModel):
    sources: list[str]
    targets: list[str]
    rules: list[str]


@lp.readonly("sources")
@lp.readonly("targets")
@lp.readonly("rules")
class Mapper:

    config_class = MapperConfig

    def __init__(self, config: MapperConfig | dict):

        if not isinstance(config, MapperConfig):
            config = MapperConfig(
                sources=config["sources"],
                targets=config["targets"],
                rules=config["rules"],
            )

        self._sources = config.sources
        self._targets = config.targets
        self._rules = config.rules

        self._parser = lmp.LOERICMapperParser()
        self._engine = lme.MatrixEngine(sources=config.sources, targets=config.targets)

        # parse rules
        for rule in config.rules:
            # process in the engine
            rule = self._parser.parse(rule)
            self._engine.process(rule)

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
        values = self._engine.get(as_array=as_array)
        return values
