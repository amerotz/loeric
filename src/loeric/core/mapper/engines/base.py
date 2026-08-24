import numpy as np

import loeric.core.element as le
import loeric.core.mapper.parameter as lmp
import loeric.core.mapper.parser.models as lmpm


class LOERICMapperEngine:
    """Process LOERICRuleObjects to implement the Mapper rules.

    The engine behaviour for the object ``SomeObjectName``
    can be defined by overriding the corresponding
    function ``_process_some_object_name``.

    The ``Mapper`` calls ``meth:set`` to set values,
    ``meth:update`` to perform the calculations
    and ``meth:get`` to obtain the resulting values.
    """

    def __init__(self, sources: list[str], targets: list[str]):

        self._parameters: dict[str, lmp.Parameter] = {}

        self._function_registry = {
            lmpm.MapperRange: self._process_mapper_range,
            lmpm.ContourTarget: self._process_contour_target,
            lmpm.ContourSource: self._process_contour_source,
            lmpm.Constant: self._process_constant,
            lmpm.HumanImpactTarget: self._process_human_impact_target,
            lmpm.ProcessedSource: self._process_processed_source,
            lmpm.MapperSelector: self._process_mapper_selector,
            lmpm.MapperRemapper: self._process_mapper_remapper,
            lmpm.MapperModulator: self._process_mapper_modulator,
            lmpm.MapperRouter: self._process_mapper_router,
        }

    def __setitem__(self, key: str, value: float) -> None:
        """Set the control named ``key`` to ``value``."""
        if key not in self._parameters:
            self._parameters[key] = lmp.Parameter(key)
        self._parameters[key].set(value)

    def __getitem__(self, key: str) -> float:
        """Get the value of control named ``key``."""
        return self._parameters[key].get()

    def set(self, inputs: list[le.LOERICElement]):
        """Set input values."""
        for el in inputs:
            if isinstance(el, le.ContourValue):
                self.__setitem__(el.name, el.value)

    def get(self, as_array=False):
        """Get output values."""
        params = self._parameters
        if as_array:
            return np.array([params[p].get() for p in params])
        else:
            return [
                le.ContourValue(
                    name=p, value=params[p].get(), time=le.PerformanceClock.now()
                )
                for p in params
            ]

    def reset(self):
        """Reset all parameters."""
        for p in self._parameters:
            self._parameters[p].reset()


    def _process_mapper_range(self, obj: lmpm.MapperRange):
        pass

    def _process_contour_target(self, obj: lmpm.Target):
        pass

    def _process_contour_source(self, obj: lmpm.ContourSource):
        pass

    def _process_constant_source(self, obj: lmpm.ConstantSource):
        pass

    def _process_human_impact_target(self, obj: lmpm.HumanImpactTarget):
        pass

    def _process_processed_source(self, obj: lmpm.ProcessedSource):
        pass

    def _process_mapper_selector(self, obj: lmpm.MapperSelector):
        pass

    def _process_mapper_remapper(self, obj: lmpm.MapperRemapper):
        pass

    def _process_mapper_modulator(self, obj: lmpm.MapperModulator):
        pass

    def _process_mapper_router(self, obj: lmpm.MapperRouter):
        pass

    def process(self, obj: lmpm.LOERICRuleObject):
        """Process the LOERICRuleObject."""
        if type(obj) in self._function_registry:
            return self._function_registry[type(obj)](obj)
        else:
            raise ValueError(f"Invalid object type {type(obj)}")
