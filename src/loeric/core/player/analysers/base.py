import logging

import pydantic as pdt

import loeric.core.element as le

logger = logging.getLogger(__name__)


class AnalyserConfig(pdt.BaseModel):
    """Base config for all analysers.

    :param type: analyser type string used by the registry.
    """

    type: str
    model_config = {"extra": "allow"}


class Analyser:
    """Base class for all input analysers.

    Subclasses implement :meth:`update` to consume incoming data and
    :meth:`get` to return the resulting :class:`~loeric.core.element.LOERICElement` list.
    """

    config_class: type[AnalyserConfig] = AnalyserConfig

    def __init__(self, type: str, **kwargs):
        """Initialise the analyser.

        :param type: analyser type identifier.
        """
        self._type = type

    def update(self, x):
        """Update the internal state with new input data.

        :param x: incoming data (audio frame or MIDI message depending on subclass).
        """
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the result of the last update step.

        :return: list of :class:`~loeric.core.element.LOERICElement` produced since last call.
        """
        return []

    def reset(self):
        """Reset internal state."""
        pass
