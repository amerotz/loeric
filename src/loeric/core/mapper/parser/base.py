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

"""Parse the Mapper's rules."""

import lark

import loeric.core.mapper.parser.transformer as lmt


class LOERICMapperParser:
    """Parse the Mapper's rules.

    Utilises a Lark parser under the hood and transforms
    nodes into LOERICRuleObjects.
    """

    GRAMMAR = r"""
        identifier: /([a-zA-Z_-][a-zA-Z0-9_-]*)/

        source : identifier
        target : identifier
        number : SIGNED_NUMBER

        rule : modulation_rule
            | pre_processing_rule
            | routing_rule

        select : source "@" range
        clip : source "|" range

        ?modulation_source : source
            | select
            | clip
        modulation_targets : [source ("," source)*]
        modulation_rule : modulation_source "~" modulation_targets

        range : "[" number "," number "]"
        ?pre_processing_rule :
            | source
            | select
            | clip
            | pre_processing_rule ">" range -> map
            | pre_processing_rule "!" -> invert

        ?routing_source : number -> constant
            | source
            | select
            | clip
            | "$" source -> processed_source
        ?routing_target : "%" source -> impact_target
            | target

        routing_target_list : [routing_target ("," routing_target)*]

        routing_rule : routing_source ":" routing_target_list

        %import common.ESCAPED_STRING
        %import common.SIGNED_NUMBER
        %import common.WS
        %ignore WS
    """

    _parser = lark.Lark(
        GRAMMAR, start="rule", parser="lalr", transformer=lmt._LOERICMapperTransformer()
    )

    def parse(self, rule: str):
        """Parse the rule string.

        Returns the transformed string as mapper models.
        """
        return self._parser.parse(rule)
