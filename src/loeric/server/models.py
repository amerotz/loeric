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
