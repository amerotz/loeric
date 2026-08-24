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

    """
    if not config.active:
        interface = OutputInterface()
        return interface
    """

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
