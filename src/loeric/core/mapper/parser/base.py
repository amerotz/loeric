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

        ?modulation_source : source
            | select
        modulation_targets : [source ("," source)*]
        modulation_rule : modulation_source "~" modulation_targets

        range : "[" number "," number "]"
        ?pre_processing_rule : select
            | pre_processing_rule ">" range -> map
            | pre_processing_rule "!" -> invert

        ?routing_source : number -> constant
            | source
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
