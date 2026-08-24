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

from loeric.core.modules.buffers import (
    DelayBufferModule,
    HistoryBufferModule,
)
from loeric.core.modules.drones import DroneModule
from loeric.core.modules.dynamics import DynamicsModule
from loeric.core.modules.harmony import HarmonyModule
from loeric.core.modules.legato import LegatoModule
from loeric.core.modules.ornament import OrnamentModule
from loeric.core.modules.swing import SwingModule
from loeric.core.modules.timing import TimingModule
from loeric.core.modules.transpose import TransposeModule
from loeric.core.modules.utils import (
    ConditionalModule,
    LoggerModule,
    TaggerModule,
)


def create_module(module_name: str, **kwargs):
    """Instantiate a module by name, validating *kwargs* against its config model.

    :param module_name: registered module name (``#`` suffixes are stripped).
    :param kwargs: raw config values; validated and coerced by the module's
        :class:`ModuleConfig` subclass before the module is constructed.
    :return: a configured :class:`LOERICModule` instance.
    :raises ValueError: if *module_name* is not registered.
    :raises pydantic.ValidationError: if *kwargs* fail config validation.
    """
    module_name = module_name.split("#")[0]

    _registry = {
        "legato": LegatoModule,
        "swing": SwingModule,
        "dynamics": DynamicsModule,
        "transpose": TransposeModule,
        "timing": TimingModule,
        "delay_buffer": DelayBufferModule,
        "history_buffer": HistoryBufferModule,
        "ornament": OrnamentModule,
        "drones": DroneModule,
        "harmony": HarmonyModule,
        "logger": LoggerModule,
        "conditional": ConditionalModule,
        "tagger": TaggerModule,
    }

    cls = _registry.get(module_name)
    if cls is None:
        raise ValueError(f"Invalid module name '{module_name}'.")

    config = cls.config_class.model_validate(kwargs)

    return cls(**config.model_dump())
