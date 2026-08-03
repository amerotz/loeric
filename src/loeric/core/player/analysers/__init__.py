"""Analyser subpackage.

Import order matters: ``base`` first (no internal deps), then submodules,
then the factory which needs all of them.
"""

from loeric.core.player.analysers.base import Analyser, AnalyserConfig

"""
"""
from loeric.core.player.analysers.audio import (
    RMS,
    AudioAnalyser,
)
from loeric.core.player.analysers.midi import (
    MIDIAnalyser,
    MIDIContourAnalyser,
    MIDILogger,
)

__all__ = [
    Analyser,
    AnalyserConfig,
    AudioAnalyser,
    RMS,
    MIDIAnalyser,
    MIDIContourAnalyser,
    MIDILogger,
]


def create_analyser(
    config: dict,
    active: bool,
    samplerate: int = None,
) -> Analyser:
    """Instantiate an analyser from a raw config dict.

    The registry lives here rather than in ``base.py`` to avoid circular
    imports — this module is the only one that knows about all subclasses.

    :param config: analyser config dict. Must contain a ``type`` key.
    :param samplerate: audio sample rate passed to audio analysers.
    :return: a configured :class:`Analyser` subclass instance.
    :raises ValueError: if ``config["type"]`` is not recognised.
    """
    _registry: dict[str, type[Analyser]] = {
        "rms": RMS,
        "midi_cc": MIDIContourAnalyser,
        "midi_logger": MIDILogger,
    }

    # make sure that analyser is active
    # only when the interface is active
    # and the user enabled that analyser
    config["active"] = config["active"] and active

    cls = _registry.get(config["type"])
    if cls is None:
        raise ValueError(f"Unknown analyser type '{config['type']}'.")

    raw = dict(config)
    if issubclass(cls, AudioAnalyser):
        raw["samplerate"] = samplerate

    validated = cls.config_class.model_validate(raw)
    return cls(**validated.model_dump())
