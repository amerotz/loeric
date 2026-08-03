from loeric.core.player.inputs.base import InputInterface, InputInterfaceConfig

"""
"""
from loeric.core.player.inputs.audio import AudioInput
from loeric.core.player.inputs.midi import MIDIInput

__all__ = [InputInterface, InputInterfaceConfig]


def create_input(config: dict | InputInterfaceConfig) -> InputInterface:
    """Instantiate the appropriate input from a config dict.

    :param config: interface configuration.
        Must contain ``active`` and ``type`` keys.
    :return: a :class:`MIDIInput` or :class:`AudioInput` instance,
        or ``InputInterface`` (uninitialised) if ``active`` is false.
    :raises ValueError: if ``config["type"]`` is not recognised.
    """
    if not isinstance(config, InputInterfaceConfig):
        config = InputInterfaceConfig(config)

    _registry = {"midi": MIDIInput, "audio": AudioInput}
    cls = _registry.get(config.type)
    if cls is None:
        raise ValueError(f"Unknown input interface type {config.type}.")

    cfg = dict(config)

    validated = cls.config_class.model_validate(cfg)
    return cls(**validated.model_dump())
