from loeric.core.player.outputs.base import OutputInterface, OutputInterfaceConfig

"""
"""
from loeric.core.player.outputs.data import DataOutput
from loeric.core.player.outputs.midi import MIDIOutput
from loeric.core.player.outputs.soundfont import SoundfontOutput

try:
    import pyqtgraph

    PYQT_AVAILABLE = True
except Exception:
    import logging

    logger = logging.getLogger(__name__)
    logger.error(
        "Could not find packages PyQt-related packages. The 'VisualOutput' port will not be available."
    )
    PYQT_AVAILABLE = False

if PYQT_AVAILABLE:
    from loeric.core.player.outputs.visual import VisualOutput

__all__ = [OutputInterface, OutputInterfaceConfig]


def create_output(config: dict | OutputInterfaceConfig) -> OutputInterface:
    """Instantiate the appropriate output interface from a config dict.

    :param config: interface configuration. Must contain ``active`` and ``type`` keys.
    :return: a concrete :class:`OutputInterface` subclass instance,
        or an inactive :class:`OutputInterface` if ``active`` is false.
    :raises ValueError: if ``config["type"]`` is not recognised.
    """
    if not isinstance(config, OutputInterfaceConfig):
        config = OutputInterfaceConfig(config)

    if not config.active:
        interface = OutputInterface()
        return interface

    # del config.active

    _registry = {
        "midi": MIDIOutput,
        "soundfont": SoundfontOutput,
        "data": DataOutput,
    }

    if PYQT_AVAILABLE:
        _registry["visual"] = VisualOutput

    cls = _registry.get(config.type)
    if cls is None:
        raise ValueError(f"Unknown output interface type {config.type}.")

    cfg = dict(config)

    validated = cls.config_class.model_validate(cfg)
    return cls(**validated.model_dump())
