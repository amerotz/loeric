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

"""Analyser subpackage.

Import order matters: ``base`` first (no internal deps), then submodules,
then the factory which needs all of them.
"""

from typing import Annotated

import pydantic as pdt

from loeric.core.player.analysers.audio import (
    RMS,
    AudioAnalyser,
    BetterRMS,
    BetterRMSConfig,
    RMSConfig,
    TempoAnalyser,
    TempoAnalyserConfig,
)
from loeric.core.player.analysers.base import Analyser
from loeric.core.player.analysers.midi import (
    MIDIAnalyser,
    MIDIContourAnalyser,
    MIDIContourAnalyserConfig,
    MIDILogger,
    MIDILoggerConfig,
)
from loeric.core.player.analysers.osc import (
    OSCContourAnalyser,
    OSCContourAnalyserConfig,
    OSCLogger,
    OSCLoggerConfig,
)

AllAnalysersConfig = Annotated[
    RMSConfig
    | BetterRMSConfig
    | TempoAnalyserConfig
    | MIDIContourAnalyserConfig
    | MIDILoggerConfig
    | OSCContourAnalyserConfig
    | OSCLoggerConfig,
    pdt.Field(discriminator="type"),
]

__all__ = [AllAnalysersConfig, AudioAnalyser, MIDIAnalyser]


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
        "better_rms": BetterRMS,
        "tempo": TempoAnalyser,
        "midi_cc": MIDIContourAnalyser,
        "midi_logger": MIDILogger,
        "osc_cc": OSCContourAnalyser,
        "osc_logger": OSCLogger,
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
    print(raw)

    validated = cls.config_class.model_validate(raw)
    print(validated.model_dump())
    return cls(**validated.model_dump())
