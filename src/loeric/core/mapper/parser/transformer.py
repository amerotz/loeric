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

import lark

import loeric.core.mapper.parser.models as lmm


class _TransformerContext:

    last_recorded_range = None

    def reset(self):
        self.last_recorded_range = None


class _LOERICMapperTransformer(lark.Transformer):

    modulation_targets = list
    routing_target_list = list

    def __init__(self):
        self._context = _TransformerContext()
        self._context.reset()

    def rule(self, items):
        self._context.reset()

        items = items[0]
        return items

    def identifier(self, s):
        (s,) = s
        return str(s)

    def source(self, s):
        (s,) = s
        return lmm.ContourSource(name=s)

    def target(self, s):
        (s,) = s
        return lmm.ContourTarget(name=s)

    def impact_target(self, s):
        (s,) = s
        return lmm.HumanImpactTarget(source=s)

    def processed_source(self, s):
        (s,) = s
        return lmm.ProcessedSource(source=s)

    def number(self, n):
        (n,) = n
        return float(n)

    def constant(self, n):
        (n,) = n
        return lmm.Constant(value=n)

    def routing_rule(self, items):
        return lmm.MapperRouter(source=items[0], targets=items[1])

    def modulation_rule(self, items):
        return lmm.MapperModulator(source=items[0], targets=items[1])

    def range(self, items):
        return lmm.MapperRange(a=items[0], b=items[1])

    def select(self, items):
        self._context.last_recorded_range = items[1]
        return lmm.MapperSelector(source=items[0], range=items[1])

    def map(self, items):

        if self._context.last_recorded_range is None:
            s_r = lmm.MapperRange(a=0, b=1)
        else:
            s_r = self._context.last_recorded_range
        m = lmm.MapperRemapper(source=items[0], source_range=s_r, target_range=items[1])
        self._context.last_recorded_range = items[1]
        return m

    def invert(self, items):

        if self._context.last_recorded_range is not None:
            s_r = self._context.last_recorded_range
            invert_range = lmm.MapperRange(
                a=1 - self._context.last_recorded_range.a,
                b=1 - self._context.last_recorded_range.b,
            )
        else:
            s_r = lmm.MapperRange(a=0, b=1)
            invert_range = lmm.MapperRange(a=1, b=0)

        self._context.last_recorded_range = invert_range
        return lmm.MapperRemapper(
            source=items[0], source_range=s_r, target_range=invert_range
        )
