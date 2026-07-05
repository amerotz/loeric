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

"""The Mapper is responsible for the routing and weighting of signals.

Inputs and outputs are declared in the 'mapping' filed of the config,
respectively in 'sources' and 'targets'.

The 'rules' section contains a list of rules to map the two.

Rules are in this format:

RULE := PRE_PROCESSING_RULE | MODULATION_RULE | ROUTING_RULE

MODULATION_RULE := source ~ MOD_TARGETS

MOD_TARGETS := source | source,MOD_TARGETS

PRE_PROCESSING_RULE :=
    source |
    source @ range |
    PRE_PROCESSING_RULE > range |
    PRE_PROCESSING_RULE !

ROUTING_RULE := IMPACT_RULE | PROCESSING_RULE

IMPACT_RULE := number : %source

PROCESSING_RULE :=
    number : ROUTING_TARGETS |
    $source : ROUTING_TARGETS |
    source : ROUTING_TARGETS

ROUTING_TARGETS: target | TARGET_EL,ROUTING_TARGETS

"""

import logging
from collections import defaultdict

import numpy as np

logger = logging.getLogger(__name__)


class Parameter:
    """A parameter that can be used by the mapper.

    Supports division in multiple ranges.
    """

    __slots__ = ("_name", "_min_value", "_max_value", "_value")

    def __init__(self, name, min_value=-np.inf, max_value=np.inf):
        self._name = name

        self._min_value, self._max_value = np.round(min_value, 2).astype(
            float
        ), np.round(max_value, 2).astype(float)

        self._value = np.nan

    def set(self, value):
        """Set the parameter."""
        if value >= self._min_value and value <= self._max_value:
            self._value = value
        else:
            self._value = np.nan

    def get(self):
        """Get the parameter value, optionally a dict with value for every range where it fits, otherwise 0."""
        return self._value

    def reset(self):
        self._value = np.nan

    def __repr__(self):
        return f"(Param '{self._name}' v={self._value}, r=[{self._min_value},{self._max_value}]"

    @staticmethod
    def basename(x: str):
        return x.split("@")[0].replace("$", "").replace("%", "")


class LOERICMatrix:

    def __init__(self, inputs: list[str]):
        self._inputs = sorted(inputs)

        self._matrix = np.zeros(len(inputs), len(inputs))
        self._bias = np.zeros(len(inputs))

    def __call__(self, x: np.array) -> np.array:
        """Execute M.T @ x + b."""
        return self.matrix.T @ x + self._bias

    @property
    def matrix(self):
        return self._matrix


class GateLayer(LOERICMatrix):

    def __init__(self, inputs: list[str]):
        self._inputs = sorted(inputs)
        n = len(inputs)

        self._matrix = np.eye(n, n)
        self._bias = np.zeros(n)

    def reset(self):
        np.fill_diagonal(self._matrix, 1.0)
        self._bias[:] = 0.0

    def set(self, key, is_open):

        index = self._inputs.index(key)
        self._matrix[:, index] *= float(is_open)
        self._bias[index] *= float(is_open)


class PreProcessingLayer(LOERICMatrix):

    def __init__(self, inputs: list[str]):
        self._inputs = sorted(inputs)

        self._matrix = np.eye(len(inputs), len(inputs))
        self._bias = np.zeros(len(inputs))

    def map_range(self, key: str, a: float, b: float, c: float, d: float):

        index = self._inputs.index(key)

        self._matrix[index][index] *= (d - c) / (b - a)
        self._bias[index] *= (d - c) / (b - a)
        self._bias[index] += c + a * (c - d) / (b - a)


class RuleLayer(LOERICMatrix):

    def __init__(self, inputs: list[str], outputs: list[str]):

        self._inputs = sorted(inputs)
        self._outputs = sorted(outputs)

        self._matrix = np.zeros((len(inputs), len(outputs)))
        self._bias = np.zeros(len(outputs))
        self._dynamic_weights = []

    def link(
        self, source: str, target: str, weight: float | Parameter = 1, fun=lambda x: x
    ):
        """Couple a source to a target (default weight = 1).

        If a Parameter is passed as weight, the weight will change with it.
        Optionally  provide a function to execute on param when it updates.
        """
        assert source in self._inputs, f"'{source}' is not a valid input."
        assert target in self._outputs, f"'{target}' is not a valid ouput."

        s_i = self._inputs.index(source)
        t_i = self._outputs.index(target)

        if isinstance(weight, Parameter):
            # check that we are not stacking parameters
            entries = [(s, t, id(w)) for s, t, w, _ in self._dynamic_weights]
            if (s_i, t_i, id(weight)) not in entries:
                self._dynamic_weights.append((s_i, t_i, weight, fun))
                self._matrix[s_i][t_i] = weight.get()
        else:
            self._matrix[s_i][t_i] = weight

    def has_sources(self, name):
        """Check if a target has sources."""
        t_i = self._outputs.index(name)
        return np.any(self._matrix[:, t_i] != 0)

    def has_output(self, name):
        """Check if a given output name is available."""
        return name in self._outputs

    def copy_rules(self, source, target):
        """Copy the rules for source into target.

        e.g. if velocity is modulated by intensity and then output to expression,
        copy the contents of $velocity to expression.

        """
        assert source in self._outputs, f"'{source}' is not a valid ruleset source."
        assert (
            target in self._outputs
        ), f"'{target}' is not a valid ruleset destination."

        s_i = self._outputs.index(source)
        t_i = self._outputs.index(target)

        # copy the column
        self._matrix[:, t_i] += self._matrix[:, s_i]

        # copy the dynamic weights
        new_w = []
        for entry in self._dynamic_weights:
            input_row, target_column, parameter, function = entry
            # if input_row goes to source column
            if target_column == s_i:
                # replicate the behaviour on the new column
                new_w.append((input_row, t_i, parameter, function))

        self._dynamic_weights.extend(new_w)

    def set_constant(self, x: float, target: str):
        assert (
            target in self._outputs
        ), f"'{target}' is not a valid ruleset destination."

        t_i = self._outputs.index(target)
        self._bias[t_i] = x

    @property
    def matrix(self):

        # reset all dynamic entries
        for s_i, t_i, _, __ in self._dynamic_weights:
            self._matrix[s_i][t_i] = 0

        # recompute them
        for s_i, t_i, w, fun in self._dynamic_weights:
            self._matrix[s_i][t_i] += fun(w.get())

        return self._matrix


class Mapper:

    def __init__(self, config):

        # initialise params
        self._parameters = {}
        self._input_names = []
        self._output_names = []
        self._impact_names = []

        for s in config["sources"]:
            # add input
            self._parameters[s] = Parameter(s)
            self._input_names.append(s)
            # add identity output
            self._output_names.append(s)

            # impact version
            name = f"%{s}"
            self._parameters[name] = Parameter(name)
            self._impact_names.append(name)

            # add processed output
            proc_name = f"${s}"
            self._output_names.append(proc_name)
            self._parameters[proc_name] = Parameter(proc_name)

        for t in config["targets"]:
            self._output_names.append(t)

            # create parameter
            self._parameters[t] = Parameter(t)

        self._output_names.sort()
        self._impact_names.sort()

        rules = sorted(
            config["rules"],
            reverse=True,
            key=lambda x: (
                "!" in x or ">" in x,
                "%" in x,
                "$" not in x,
            ),
        )
        self._create_ranged_input_names(rules)

        logger.debug(self._input_names)
        logger.debug(self._output_names)
        logger.debug(self._impact_names)

        # create pre processing
        self._pre_layer = PreProcessingLayer(self._input_names)

        # create filter
        self._gate_layer = GateLayer(self._input_names)

        # create human impact matrix
        self._impact_layer = RuleLayer(self._input_names, self._impact_names)

        # create routing matrix
        self._rule_layer = RuleLayer(self._input_names, self._output_names)

        print(rules)
        self._fill_matrices(rules)

        self._ranged_input_pairs = [
            (p, Parameter.basename(p))
            for p in self._input_names
            if Parameter.basename(p) != p
        ]
        self._plain_input_names = [
            p for p in self._input_names if Parameter.basename(p) == p
        ]

    def reset(self):
        for p in self._parameters:
            self._parameters[p].reset()

    def _fill_matrices(self, rules: list[str]):
        """Populate the pre-processing matrix, the human impact matrix and the rule matrix according to the specified rules."""
        # identity routing
        for name in self._output_names:
            if name in self._input_names:
                self._rule_layer.link(name, name)

        action_dict = defaultdict(lambda: None)

        # output routing
        action_dict[":"] = "route"
        # modulation
        action_dict["~"] = "modulate"
        # range select
        action_dict["@"] = "select"
        # mapping
        action_dict[">"] = "map"
        # inversion
        action_dict["!"] = "invert"

        for rule in rules:

            elements = rule.split(" ")

            source = self._parse_source(elements[0])

            source_range = (0, 1)
            current_action = None

            for el in elements[1:]:

                if current_action is not None:

                    source, source_range = self._apply_action(
                        current_action, el, source, source_range
                    )

                current_action = action_dict[el]

                # invert executes immediately
                if current_action == "invert":

                    # obtain mapping extremes
                    a, b = source_range
                    c, d = 1 - a, 1 - b
                    source_range = self._apply_map(source, a, b, c, d)
                    current_action = None

        # couple the ones that have no coupling
        for name in self._input_names:
            dest = f"${name}"
            if self._rule_layer.has_output(dest) and not self._rule_layer.has_sources(
                dest
            ):
                self._rule_layer.link(name, dest)

    def _apply_action(self, action, el, source, source_range):
        """Parse the current element by implementing the functions connected to the specified action.

        The select and map actions update source_range, which is returned accordingly (unaltered in the case of other actions).

        select updates source, which is returned accordingly.

        The routing and modulation operations terminate parsing returning a flag.
        """
        if action == "route":

            other_targets = el.split(",")

            # make sure that impact and processig rules
            # are not mixed together
            all_same = True
            if "%" in el:
                for t in other_targets:
                    all_same = all_same and "%" in t

            assert (
                all_same
            ), f"{other_targets} is an invalid set of destinations. Human impact and other targets cannot be mixed. Write separate rules instead."

            for t in other_targets:
                self._parse_action_route(source, t)

        elif action == "modulate":

            other_sources = el.split(",")

            for source_2 in other_sources:
                self._parse_action_modulate(source, source_2)

        elif action == "select":
            # update source to select range
            source += "@" + el
            source_range = Mapper.parse_range(el)

        elif action == "map":
            a, b = source_range
            c, d = Mapper.parse_range(el)
            source_range = self._apply_map(source, a, b, c, d)
        else:
            raise ValueError(f"Unknown action '{action}'")

        return source, source_range

    def _apply_map(self, source, a, b, c, d):
        assert (
            not isinstance(source, float) and "$" not in source
        ), f"Only raw inputs can be remapped, not '{source}'."
        assert a != b, f"Source range [{a},{b}] is invalid."

        # obtain mapping extremes

        # update mapping
        # the origin range must always be sorted
        # the target range can be inverted
        self._pre_layer.map_range(source, min(a, b), max(a, b), c, d)

        # update source exremes if chaining multiple maps
        return c, d

    def _parse_source(self, string: str):
        """Parse the source string."""
        # create source
        source = string
        # if a number, parse it
        try:
            source = float(source)
        except ValueError:
            pass

        # if not number
        if isinstance(source, str):
            # processed version must
            # have an associated input
            name = source
            if source.startswith("$"):
                name = source.replace("$", "")

            assert (
                name in self._input_names
            ), f"'{source}' is not a valid source (must be an input)."

        return source

    def _parse_action_route(self, source, target):
        """Redirect the value of source to target without modulation."""
        assert (
            "$" not in target and "@" not in target and target not in self._input_names
        ), f"'{target}' can only appear as a source, not routing destination."

        # this is a constant, so only set the parameter
        if isinstance(source, float):
            # change the parameter
            self._parameters[target].set(source)

            # reflect in the matrix
            if target.startswith("%"):
                self._impact_layer.set_constant(source, target)
            # main matrix
            else:
                self._rule_layer.set_constant(source, target)

        # $source is the processed version of source
        # this means copying the matrix column of $source
        # into target
        elif source.startswith("$"):
            self._rule_layer.copy_rules(source, target)

        # redirect one contour to the other
        else:
            # if this is a weight
            if target.startswith("%"):
                self._impact_layer.link(source, target)
            # main matrix
            else:
                self._rule_layer.link(source, target)

    def _parse_action_modulate(self, source_1: str, source_2: str):
        """Implement modulation of source_2 through source_1.

        e.g. _parse_action_modulate(intensity, velocity) fills the matrix so that:

        ```
        $velocity = intensity * %velocity + velocity * (1 - %velocity)
        ```
        """
        assert (
            "$" not in source_1
        ), f"Processed value '{source_1}' can only be routed to outputs, not act as modulator."
        assert (
            "$" not in source_2
        ), f"Processed value '{source_2}' can only be routed to outputs, not modulated."

        assert (
            source_1 in self._input_names
        ), f"Modulator '{source_1}' can only be an input."

        assert (
            source_2 in self._input_names
        ), f"Modulated '{source_2}' can only be an input."

        # obtain impact param
        name = f"%{source_2}"
        param = self._parameters[name]

        # the processed version of source
        target = f"${source_2}"

        self._rule_layer.link(source_1, target, param)
        self._rule_layer.link(source_2, target, param, lambda x: 1 - x)

    @staticmethod
    def parse_range(s: str) -> tuple[float, float]:
        """Parse a range string"""
        s = s.strip()

        if not (s.startswith("[") and s.endswith("]")):
            raise ValueError("Expected format: [a,b]")

        inner = s[1:-1]
        parts = inner.split(",")

        if len(parts) != 2:
            raise ValueError("Expected exactly two values")

        try:
            a = float(parts[0].strip())
            b = float(parts[1].strip())
        except ValueError as e:
            raise ValueError("Both values must be numbers") from e

        return (a, b)

    def _create_ranged_input_names(self, rules):
        # @ creates subdivisions of the input range
        # $ is handled at the end
        # because $ is a meta operator
        # to reference the processed version
        # of a signal
        rules = [r for r in rules if "@" in r]

        # go through each
        for rule in rules:

            # tokenise
            elements = rule.split(" ")

            # well formed
            if elements[1] != "@":
                raise Exception("Selector can only occur right after source.")

            source = self._parse_source(elements[0])

            assert (
                not isinstance(source, float) and "$" not in source
            ), f"Range selection cannot be performed on '{source}'"

            # range
            a, b = Mapper.parse_range(elements[2])

            name = "".join(elements[:3])

            # add range
            if name not in self._parameters:
                self._parameters[name] = Parameter(name, float(a), float(b))

                self._input_names.append(name)

        self._input_names.sort()

    def __setitem__(self, key: str, value: float) -> None:
        """Set the control named ``key`` to ``value``."""
        if key not in self._parameters:
            self._parameters[key] = Parameter(key)
        self._parameters[key].set(value)

    def __getitem__(self, key: str) -> float:
        """Get the value of control named ``key``."""
        return self._parameters[key].get()

    def update(self):
        """Updates output values given inputs and the specified routing."""
        inputs = self._preprocess_inputs()
        params = self._parameters

        for i, v in zip(self._input_names, inputs):
            params[i].set(v)

        impact_values = self._impact_layer(np.nan_to_num(inputs, nan=0))

        # set new human impact
        for i, v in zip(self._impact_names, impact_values):
            params[i].set(v)

        outputs = self._rule_layer(inputs)

        for o, v in zip(self._output_names, outputs):
            params[o].set(v)

    def _preprocess_inputs(self):
        """Apply range selection and mapping to inputs."""
        params = self._parameters

        for name, base in self._ranged_input_pairs:
            params[name].set(params[base].get())

        inputs = self._input_values

        # create gate
        gate = self._gate_layer
        gate.reset()
        for i, val in enumerate(inputs):
            if np.isnan(val):
                gate.set(self._input_names[i], False)

        inputs = np.nan_to_num(inputs, nan=0)

        # remap
        out = self._pre_layer(inputs)

        # filter
        out = gate(out)

        return out

    @property
    def _input_values(self):
        params = self._parameters
        return np.array([params[n].get() for n in self._input_names])

    @property
    def _impact_values(self):
        params = self._parameters
        return np.array([params[n].get() for n in self._impact_names])

    def set(self, inputs: dict):
        for key in inputs:
            self.__setitem__(key, inputs[key])

    def get(self, as_array=False):
        params = self._parameters
        if as_array:
            return np.array([params[p].get() for p in params])
        else:
            return {p: params[p].get() for p in params}
