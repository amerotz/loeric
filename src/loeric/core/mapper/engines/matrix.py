import numpy as np

import loeric.core.element as le
import loeric.core.mapper.engines.base as lme
import loeric.core.mapper.parameter as lmp
import loeric.core.mapper.parser.models as lmPm


class LOERICMatrix:
    """A matrix for LOERIC mapper calculations.

    A mapper step is implemented as a linear combination of inputs.
    """

    def __init__(self):
        self._inputs = []
        self._outputs = []
        self._matrix = None
        self._bias = None

    def add_input(self, name: str):
        """Append a row to the matrix if not already present."""
        # duplicates not allowed
        if name in self._inputs:
            return

        # add to list
        self._inputs.append(name)

        # if there are outputs
        if len(self._outputs) != 0:
            # this is the first input
            # added after outputs
            if self._matrix is None:
                # create the matrix
                self._matrix = np.zeros((len(self._inputs), len(self._outputs)))
            # matrix is initialised
            # just add the row
            else:
                self._matrix = np.append(
                    self._matrix, np.zeros((1, len(self._outputs))), axis=0
                )
        # ensure identity coupling
        if name in self._outputs:
            s_i = self._inputs.index(name)
            o_i = self._outputs.index(name)
            self._matrix[s_i][o_i] = 1

    def add_output(self, name: str):
        """Append a column to the matrix if not already present."""
        # duplicates not allowed
        if name in self._outputs:
            return

        # add to list
        self._outputs.append(name)
        # add bias (not dependent on input)
        if self._bias is None:
            self._bias = np.zeros(1)
        else:
            self._bias = np.append(self._bias, 0)

        # if there are outputs
        if len(self._inputs) != 0:
            # this is the first outputs
            # added after outputs
            if self._matrix is None:
                # create the matrix
                self._matrix = np.zeros((len(self._inputs), len(self._outputs)))
            # matrix is initialised
            # just add the column
            else:
                self._matrix = np.append(
                    self._matrix, np.zeros((len(self._inputs), 1)), axis=1
                )

        # ensure identity coupling
        if name in self._inputs:
            s_i = self._inputs.index(name)
            o_i = self._outputs.index(name)
            self._matrix[s_i][o_i] = 1

    def __call__(self, x: np.array) -> np.array:
        """Execute M.T @ x + b."""
        if self._matrix is None:
            return self._bias
        return self.matrix.T @ x + self._bias

    @property
    def inputs(self):
        return self._inputs

    @property
    def outputs(self):
        return self._outputs

    @property
    def matrix(self):
        """The underlying numpy matrix."""
        return self._matrix


class GateLayer(LOERICMatrix):
    """A matrix implementing gates for range selection."""

    def __init__(self):
        super().__init__()

    def reset(self):
        np.fill_diagonal(self._matrix, 1.0)
        self._bias[:] = 0.0

    def set(self, key: str, is_open: bool):
        """Set the input indexed by ``key`` to open or closed."""
        index = self._inputs.index(key)
        self._matrix[:, index] *= float(is_open)
        self._bias[index] *= float(is_open)

    """
    def __call__(self, x: np.array) -> np.array:
        return super().__call__(x)
    """


class PreProcessingLayer(LOERICMatrix):

    def __init__(self):
        super().__init__()

    def map_range(
        self, input_key: str, output_key: str, a: float, b: float, c: float, d: float
    ):
        """Map the input ``key`` to a range."""
        if input_key not in self._inputs:
            raise ValueError(f"Unknown input {input_key}.")

        if output_key not in self._outputs:
            raise ValueError(f"Unknown output {output_key}.")

        i_index = self._inputs.index(input_key)
        o_index = self._outputs.index(output_key)

        self._matrix[i_index][o_index] *= (d - c) / (b - a)
        self._bias[o_index] *= (d - c) / (b - a)
        self._bias[o_index] += c + a * (c - d) / (b - a)

    def route(self, input_key: str, output_key: str):
        """Route a source to a target."""

        if input_key not in self._inputs:
            raise ValueError(f"Unknown input {input_key}.")

        if output_key not in self._outputs:
            raise ValueError(f"Unknown output {output_key}.")

        i_index = self._inputs.index(input_key)
        o_index = self._outputs.index(output_key)

        self._matrix[i_index][o_index] = 1


class RuleLayer(LOERICMatrix):

    def __init__(self):

        super().__init__()

        self._dynamic_weights = []

    def link(
        self,
        source: str,
        target: str,
        weight: float | lmp.Parameter = 1,
        fun=lambda x: x,
    ):
        """Couple a source to a target (default weight = 1).

        If a Parameter is passed as weight, the weight will change with it.
        Optionally  provide a function to execute on param when it updates.
        """
        assert source in self._inputs, f"'{source}' is not a valid input."
        assert target in self._outputs, f"'{target}' is not a valid ouput."

        s_i = self._inputs.index(source)
        t_i = self._outputs.index(target)

        if isinstance(weight, lmp.Parameter):
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


class MatrixEngine(lme.LOERICMapperEngine):

    def __init__(self, sources: list[str], targets: list[str]):

        super().__init__(sources, targets)

        self._ranged_input_pairs = []

        # create pre processing
        self._pre_layer = PreProcessingLayer()

        # create filter
        self._gate_layer = GateLayer()

        # create human impact matrix
        self._impact_layer = RuleLayer()

        # create routing matrix
        self._rule_layer = RuleLayer()

        for s in sources:
            self._add_input(s)
            self._add_parameter(s)

        for t in targets:
            self._rule_layer.add_output(t)
            self._add_parameter(s)

    def set(self, inputs: list[le.LOERICElement]):

        super().set(inputs)

        # update ranges
        for name, base in self._ranged_input_pairs:
            self._parameters[name].set(self._parameters[base].get())

    def update(self):
        """Update output values given inputs and the specified routing.

        Called by ``meth:Mapper.update()``.
        """

        x = np.array([self._parameters[n].get() for n in self._pre_layer.inputs])

        # close and open gates
        self._gate_layer.reset()
        for i, val in enumerate(x):
            if np.isnan(val):
                self._gate_layer.set(self._gate_layer.inputs[i], False)

        # remap
        x = np.nan_to_num(x, nan=0)
        x = self._pre_layer(x)
        x = self._gate_layer(x)

        # set the parameters
        for name, val in zip(self._gate_layer.outputs, x):
            self._parameters[name].set(val)

        # calculate human impact
        x_h = np.array([self._parameters[n].get() for n in self._impact_layer.inputs])
        # if we are not offline
        if len(x_h) != 0:
            y_h = self._impact_layer(x_h)
            for name, val in zip(self._impact_layer.outputs, y_h):
                self._parameters[name].set(val)

        # calculate rules
        y = self._rule_layer(x)
        for name, val in zip(self._rule_layer.outputs, y):
            self._parameters[name].set(val)

    def _add_input(self, name):
        """Add an input to the underlying matrices."""
        # add source
        self._gate_layer.add_input(name)
        self._pre_layer.add_input(name)
        self._rule_layer.add_input(name)

        # add identity
        self._gate_layer.add_output(name)
        self._pre_layer.add_output(name)
        self._rule_layer.add_output(name)

    def _add_parameter(self, name: str, a: float = 0, b: float = 1):
        if name not in self._parameters:
            # add parameter
            self._parameters[name] = lmp.Parameter(name, a, b)

    def _process_mapper_range(self, obj: lmPm.MapperRange):
        pass

    def _process_contour_target(self, obj: lmPm.Target):

        self._rule_layer.add_output(obj.name)
        self._add_parameter(obj.name)

        return obj.name

    def _process_contour_source(self, obj: lmPm.ContourSource):

        self._add_input(obj.name)
        self._add_parameter(obj.name)

        return obj.name

    def _process_constant(self, obj: lmPm.Constant):
        return obj.value

    def _process_human_impact_target(self, obj: lmPm.HumanImpactTarget):
        source = self.process(obj.source)
        impact_name = f"%{source}"

        self._impact_layer.add_output(impact_name)
        self._add_parameter(impact_name)

        return impact_name

    def _process_processed_source(self, obj: lmPm.ProcessedSource):
        # add processed version
        source = self.process(obj.source)
        proc_name = f"${source}"

        self._rule_layer.add_output(proc_name)
        self._add_parameter(proc_name)

        return proc_name

    def _process_mapper_selector(self, obj: lmPm.MapperSelector):
        name = self.process(obj.source)

        ranged_name = f"{name}@[{obj.range.a},{obj.range.b}]"
        self._ranged_input_pairs.append((ranged_name, name))

        self._add_input(ranged_name)
        # overwrite param
        self._add_parameter(ranged_name, obj.range.a, obj.range.b)

        return ranged_name

    def _process_mapper_remapper(self, obj: lmPm.MapperRemapper):
        source_name = self.process(obj.source)

        # obtain ranges
        a, b = (
            min(obj.source_range.a, obj.source_range.b),
            max(obj.source_range.a, obj.source_range.b),
        )
        c, d = (obj.target_range.a, obj.target_range.b)

        self._pre_layer.map_range(source_name, source_name, a, b, c, d)
        return source_name

    def _process_mapper_modulator(self, obj: lmPm.MapperModulator):
        source_1 = self.process(obj.source)

        for t in obj.targets:
            source_2 = self.process(t)
            target = f"${source_2}"

            self._rule_layer.add_output(target)
            self._add_parameter(target)

            impact_name = f"%{source_2}"
            self._add_parameter(impact_name)
            param = self._parameters[impact_name]

            # base version
            self._rule_layer.link(source_1, target, param)
            # processed version
            self._rule_layer.link(source_2, target, param, lambda x: 1 - x)

    def _process_mapper_router(self, obj: lmPm.MapperRouter):
        s = self.process(obj.source)
        for target in obj.targets:
            t = self.process(target)
            if isinstance(obj.source, lmPm.Constant):
                value = s
                # change the parameter
                self._parameters[t].set(value)

                # reflect in the matrix
                if isinstance(target, lmPm.HumanImpactTarget):
                    self._impact_layer.set_constant(value, t)
                # main matrix
                elif isinstance(target, lmPm.ContourTarget):
                    self._rule_layer.set_constant(value, t)

            # $source is the processed version of source
            # this means copying the matrix column of $source
            # into target
            elif isinstance(obj.source, lmPm.ProcessedSource):

                self._add_parameter(t)
                self._rule_layer.add_output(t)
                self._rule_layer.copy_rules(s, t)

            # redirect one contour to the other
            else:
                # if this is a weight
                if isinstance(target, lmPm.HumanImpactTarget):
                    self._impact_layer.add_input(s)
                    self._impact_layer.link(s, t)
                # main matrix
                elif isinstance(target, lmPm.ContourTarget):
                    self._rule_layer.link(s, t)
