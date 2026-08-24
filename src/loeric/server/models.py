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

from typing import Optional

import pydantic as pdt


class LOERICState(pdt.BaseModel):
    running: bool = False
    current_tune: Optional[str] = None
    current_config: Optional[str] = None
    parameters: dict = {}


class StartRequest(pdt.BaseModel):
    tune: str
    config: Optional[str]
    instrument_model: str
    repetitions: int
    transpose: int
    responsiveness: float
    volume: float
    tempo: int


class TuneInfo(pdt.BaseModel):
    id: str
    name: str
    path: str


class ConfigInfo(pdt.BaseModel):
    id: str
    name: str


class TunesResponse(pdt.BaseModel):
    tunes: list[TuneInfo]


class ConfigsResponse(pdt.BaseModel):
    default_config: Optional[ConfigInfo]
    configs: list[ConfigInfo]


class InstrumentModel(pdt.BaseModel):
    id: str
    name: str


class InstrumentModelsResponse(pdt.BaseModel):
    models: list[InstrumentModel]


class StatusResponse(pdt.BaseModel):
    running: bool
    current_tune: Optional[str]
    current_config: Optional[str]
    current_instrument: Optional[str]
    parameters: dict
