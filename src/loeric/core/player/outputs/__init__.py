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

from typing import Annotated

import pydantic as pdt

from loeric.core.player.outputs.base import OutputInterface, OutputInterfaceConfig
from loeric.core.player.outputs.data import DataOutput, DataOutputConfig
from loeric.core.player.outputs.midi import MIDIOutput, MIDIOutputConfig
from loeric.core.player.outputs.osc import OSCOutput, OSCOutputConfig
from loeric.core.player.outputs.soundfont import SoundfontOutput, SoundfontOutputConfig

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

AllOutputInterfacesConfig = Annotated[
    MIDIOutputConfig | OSCOutputConfig | DataOutputConfig | SoundfontOutputConfig,
    pdt.Field(discriminator="type"),
]

if PYQT_AVAILABLE:
    from loeric.core.player.outputs.visual import VisualOutput, VisualOutputConfig

    AllOutputInterfacesConfig = Annotated[
        MIDIOutputConfig
        | OSCOutputConfig
        | DataOutputConfig
        | SoundfontOutputConfig
        | VisualOutputConfig,
        pdt.Field(discriminator="type"),
    ]


__all__ = [AllOutputInterfacesConfig]


def create_output(config: dict | OutputInterfaceConfig) -> OutputInterface:
    """Instantiate the appropriate output interface from a config dict.

    :param config: interface configuration. Must contain ``active`` and ``type`` keys.
    :return: a concrete :class:`OutputInterface` subclass instance,
        or an inactive :class:`OutputInterface` if ``active`` is false.
    :raises ValueError: if ``config["type"]`` is not recognised.
    """
    if not isinstance(config, OutputInterfaceConfig):
        config = OutputInterfaceConfig(config)

    _registry = {
        "midi": MIDIOutput,
        "soundfont": SoundfontOutput,
        "data": DataOutput,
        "osc": OSCOutput,
    }

    if PYQT_AVAILABLE:
        _registry["visual"] = VisualOutput

    cls = _registry.get(config.type)
    if cls is None:
        raise ValueError(f"Unknown output interface type {config.type}.")

    cfg = dict(config)

    validated = cls.config_class.model_validate(cfg)
    return cls(**validated.model_dump())
