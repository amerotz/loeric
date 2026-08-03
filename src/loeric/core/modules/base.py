import copy
from functools import cached_property

import nanoid as nid
from pydantic import BaseModel

import loeric.core.element as le
import loeric.core.paths as lp


class ModuleConfig(BaseModel):
    """Base config for all LOERIC modules.

    :param bypass: deactivate the module without removing it.
    :param tag: tag to apply to all output elements.
    :param required_tags: tags an element must have to be processed.
    """

    bypass: bool = False
    tag: str | None = None
    required_tags: list[str] | None = None

    model_config = {"extra": "allow"}


@lp.expose("_bypass", "bypass")
class LOERICModule:
    """A performance module implementing a series of performance rules."""

    config_class: type[ModuleConfig] = ModuleConfig

    def __init__(
        self, bypass: bool = False, tag: str = None, required_tags: list[str] = None
    ):
        """Process LOERICElements.

        :param bypass: activate or deactivate the module.
        :param tag: apply a tag to the element.
        :param required_tags: tags required for the element to be processed.
        """
        self._signature = nid.generate()
        self._name = "module"

        self._lookahead_size = 0
        self._lookback_size = 0
        self._window_size = 0

        self._bypass = bypass
        self._tag = tag
        self._required_tags = required_tags
        self._is_online = False

        self._key_signature = None
        self._time_signature = None
        self._tempo = None
        self._is_end_of_score = False

        self._contour_values = {}

    def reset(self):
        """Reset all module attributes."""
        self._key_signature = None
        self._time_signature = None
        self._tempo = None
        self._is_end_of_score = False

    def set_key_signature(self, key: le.KeySignature):
        self._key_signature = key

    def set_time_signature(self, meter: le.TimeSignature):
        self._time_signature = meter

    def set_tempo(self, tempo: le.Tempo):
        self._tempo = tempo

    def process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Process an element (only if not seen by this module already).

        Keep track of time signature, key signature and tempo and
        then call the module-specific processing function.

        :param element: the element to process.
        :param window: an optional window of events in the future.
        """
        if isinstance(element, le.TimeSignature):
            self._time_signature = copy.copy(element)
        elif isinstance(element, le.KeySignature):
            self._key_signature = copy.copy(element)
        elif isinstance(element, le.Tempo):
            self._tempo = copy.copy(element)
        elif isinstance(element, le.ContourValue):
            self._contour_values[element.name] = element.value

        return self._process(element, window)

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Module-specific process function.

        Override in modules to implement specific behaviors.
        Called by ``module.process()``.
        """
        return [element]

    def __call__(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):

        # don't accept anything after
        # the first end of score
        if isinstance(element, le.EndOfScore):
            self._is_end_of_score = True

        # if I saw this already, don't run again
        if (
            # bypass this module
            self._bypass
            # already seen by module
            or element.has_signature(self._signature)
            # does not have required tags
            or not self._contains_required_tags(element)
            # is end of score
            or self._is_end_of_score
        ):
            return [element]

        # process it
        out = self.process(element, window=window)

        # sign it
        for o in out:
            o.add_signature(self._signature, is_online=self._is_online)
            # propagate offline signatures of the original element
            o.copy_offline_signatures(element)
            # tag it
            if self._tag is not None:
                o.add_tag(self._tag)

        return out

    def _contains_required_tags(self, element: le.LOERICElement) -> bool:
        """Check if an element contains all required tags."""
        if self._required_tags is None:
            return True

        return all(element.has_tag(t) for t in self._required_tags)

    @cached_property
    def is_online(self):
        return self._is_online

    @cached_property
    def name(self):
        return self._name + "::" + self._signature

    @property
    def lookahead_size(self):
        return self._lookahead_size

    @property
    def window_size(self):
        return self._window_size
