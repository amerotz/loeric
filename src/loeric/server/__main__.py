"""FastAPI server for Loeric GUI.

Serves the static HTML interface and provides API endpoints to control loeric
"""

import importlib.resources as ir
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import loeric
import loeric.config as lc
import loeric.core.tune as tu
import loeric.server.models as lsm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
musician = None


def process_monitor():
    """Monitor the process running LOERIC to update app status."""
    global musician

    while True:
        if musician is not None:
            musician.join()

            musician = None
            state.running = False
            state.current_tune = None
            state.current_config = None

        time.sleep(0.5)


threading.Thread(
    target=process_monitor,
    daemon=True,
).start()

PORT = int(os.getenv("LOERIC_WEBAPP_PORT", 8080))

if getattr(sys, "frozen", False):
    logger.debug("Running compiled binary.")
    BASE_DIR = Path(sys._MEIPASS)
else:
    logger.debug("Running from cli.")
    BASE_DIR = Path(__file__).resolve().parents[2]

STATIC_ROOT = Path(os.getenv("LOERIC_WEBAPP_DIR", BASE_DIR / "static")).resolve()

# Configuration
INSTRUMENT_CONFIG_PATH = ir.files(loeric.config).joinpath("performance/instrument")
TUNE_CONFIG_PATH = ir.files(loeric.config).joinpath("performance/tune_type")
CONFIG_PATH = STATIC_ROOT / "configs"
CONFIG_INDEX_FILE = STATIC_ROOT / "index.json"
BASE_CONFIG = STATIC_ROOT / "configs" / "base.json"
TUNES_PATH = STATIC_ROOT / "tunes"
FRONTEND_ROOT = STATIC_ROOT / "site"
GUI_FILE = FRONTEND_ROOT / "index.html"

logger.info(f"STATIC_ROOT: {STATIC_ROOT}")
logger.info(f"TUNES_PATH: {TUNES_PATH}")
logger.info(f"CONFIG_PATH: {CONFIG_PATH}")
logger.info(f"GUI_FILE: {GUI_FILE}")

# FastAPI app
app = FastAPI(title="LOERIC")

# Global state
state = lsm.LOERICState()

# Load config index
config_index = {}
if CONFIG_INDEX_FILE.exists():
    with open(CONFIG_INDEX_FILE, "r") as f:
        config_index = json.load(f)
    logger.info(f"Loaded config index: {config_index}")
else:
    logger.warning(f"Config index not found at {CONFIG_INDEX_FILE}")


def load_tunes() -> dict[str, lsm.TuneInfo]:
    """Scan for available tunes in the tunes directory."""
    tunes = {}
    if TUNES_PATH.exists():
        for tune_file in TUNES_PATH.glob("*.abc"):
            tune_id = tune_file.stem
            tunes[tune_id] = lsm.TuneInfo(id=tune_id, name=tune_id, path=str(tune_file))

        for tune_file in TUNES_PATH.glob("*.mid"):
            tune_id = tune_file.stem
            tunes[tune_id] = lsm.TuneInfo(id=tune_id, name=tune_id, path=str(tune_file))

        logger.info(f"Found {len(tunes)} tunes")
    else:
        logger.warning(f"Tunes directory not found: {TUNES_PATH}")

    return tunes


tune_list = load_tunes()


def get_default_config(tune_id: str) -> Optional[str]:
    """Get the default configuration for a tune."""
    if tune_id in config_index:
        return config_index[tune_id].get("default")
    return None


def get_available_configs(
    tune_id: str,
) -> tuple[Optional[lsm.ConfigInfo], list[lsm.ConfigInfo]]:
    """Get configuration files for a specific tune.

    Each tune can have mutliple configuration snippets
    specifying interaction modalities, style, outputs, etc.
    By default, each tune is loaded with the relevant tune type
    and instrument configuration snippets, as well as a
    default configuration, if present. The default
    configuration should specify tweaks to the base configuration
    (e.g., phrasing, additional ornamentation for that tune),
    while other configuration files should substantially
    alter the way the tune is performed (e.g. interaction
    modalities connected to a specific performance, player, or
    radically changing LOERIC's defaults).

    :return: a tuple of (default_config, all_configs)
    """
    # this means that we should just load the tune
    if tune_id not in config_index:
        logger.warning(f"No config entry for tune: {tune_id}")
        return None, []

    tune_config = config_index[tune_id]
    configs_list = tune_config.get("configs", [])
    default_name = tune_config.get("default")

    # Create ConfigInfo objects for all configs
    config_infos = [lsm.ConfigInfo(id=c, name=c) for c in configs_list]

    # Create default config info
    default_config = None
    if default_name:
        default_config = lsm.ConfigInfo(id=default_name, name=default_name)

    return default_config, config_infos


def get_available_instruments() -> list[lsm.InstrumentModel]:
    """Get available instrument models.

    Adapt this based on how loeric defines instruments.
    For now, returning common instrument models.
    """
    instruments = []
    for file in INSTRUMENT_CONFIG_PATH.glob("*.json"):
        inst_id = file.stem
        inst_name = file.stem.capitalize()
        instruments.append(lsm.InstrumentModel(id=inst_id, name=inst_name))
    return instruments


async def start_loeric(
    tune: str,
    repetitions: int,
    transpose: int,
    config: str,
    instrument_model: str,
    tempo: float,
    volume: float,
    responsiveness: float,
) -> bool:
    """Start loeric with the specified tune and parameters.

    LOERIC will be created with the following configurations, merged in this order:
    - the base configuration `base.json`
    - the tune type configuration, inferred from the tune's time signature
    - the instrument model
    - additional configuration snippets specified in `index.json`

    Once LOERIC is created, a new thread is spawn and the system starts.
    """
    global musician
    try:

        # Update state
        state.current_tune = tune
        state.current_config = config
        state.parameters = {
            "tempo": tempo,
            "volume": volume,
            "instrument": instrument_model,
            "repetitions": repetitions,
            "transpose": transpose,
            "responsiveness": responsiveness,
        }

        # open base config
        with open(BASE_CONFIG, "r") as f:
            base = json.load(f)

        # create tune
        tune = tu.Tune(tune_list[tune].path, repetitions)
        # tune type
        with open(
            TUNE_CONFIG_PATH / f"{loeric.LOERIC.infer_tune_type(tune)}.json"
        ) as f:
            tune_config = json.load(f)

        # open instrument config
        with open(INSTRUMENT_CONFIG_PATH / f"{instrument_model}.json", "r") as f:
            instrument_config = json.load(f)

        if config is not None:
            # open tune config
            with open(CONFIG_PATH / config, "r") as f:
                config = json.load(f)
        else:
            config = {}

        config = lc.join_configs([base, tune_config, instrument_config, config])
        config = lc.process_config(config)
        if "transpose" in config["modules"]:
            config["modules"]["transpose"]["steps"] = transpose

        # create LOERIC
        if musician:
            musician.stop()
        musician = loeric.LOERIC(config=config, mode="thread")

        musician.set_tune(tune)
        musician.set_tempo(tempo)

        musician.start()

        # change responsiveness and volume
        musician.set_attribute(
            "player/input/mic_input/analysers/loudness/responsiveness", responsiveness
        )

        _change_volume(volume)

        state.running = True

        return True

    except Exception as e:
        logger.error(f"Failed to start loeric: {e}")
        raise e


async def stop_loeric() -> bool:
    """Stop the running loeric process."""
    global musician
    try:
        logger.info("Stopping loeric")

        if musician:
            musician.stop()

        musician = None

        state.running = False
        state.current_tune = None
        state.current_config = None
        state.parameters = {}

        return True
    except Exception as e:
        logger.error(f"Failed to stop loeric: {e}")
        raise


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/api/tunes", response_model=lsm.TunesResponse)
async def get_tunes():
    """GET /api/tunes - Get list of available tunes."""
    return lsm.TunesResponse(tunes=list(tune_list.values()))


@app.get("/api/configs/{tune_id}", response_model=lsm.ConfigsResponse)
async def get_configs(tune_id: str):
    """GET /api/configs/{tune_id} - Get available configurations for a tune.

    Returns the default config and list of all available configs.
    """
    default_config, configs = get_available_configs(tune_id)

    return lsm.ConfigsResponse(default_config=default_config, configs=configs)


@app.get("/api/instruments", response_model=lsm.InstrumentModelsResponse)
async def get_instruments():
    """GET /api/instruments - Get available instrument models."""
    instruments = get_available_instruments()
    return lsm.InstrumentModelsResponse(models=instruments)


@app.post("/api/tempo/{qpm}", response_model=lsm.StatusResponse)
async def tempo_change(qpm: float):
    """POST /api/tempo/{qpm} - Change LOERIC's tempo."""
    global musician
    if musician:
        musician.set_tempo(qpm)

    state.parameters["tempo"] = qpm
    return await get_status()


@app.post("/api/responsiveness/{value}", response_model=lsm.StatusResponse)
async def responsiveness_change(value: float):
    """POST /api/responsiveness/{value} - Change LOERIC's responsiveness."""
    global musician
    if musician:
        musician.set_attribute(
            "player/input/mic_input/analysers/loudness/responsiveness", value
        )

    state.parameters["responsiveness"] = value
    return await get_status()


@app.post("/api/volume/{value}", response_model=lsm.StatusResponse)
async def volume_change(value: float):
    """POST /api/volume/{value} - Change LOERIC's volume."""

    global musician

    if not musician:
        raise HTTPException(status_code=400, detail="LOERIC is not running")

    status = _change_volume(value)
    if status == -1:
        raise HTTPException(status_code=404, detail=f"Path '{path}' not found")

    state.parameters["volume"] = value
    return await get_status()


def _change_volume(value: float):
    global musician

    outputs = _get_param("player/output")

    if outputs is None:
        return -1

    for o in outputs["children"]:
        p = f"player/output/{o}"
        print(p)
        attrs = _get_param(p)
        if attrs is not None and "children" in attrs and "volume" in attrs["children"]:
            p += "/volume"
            musician.set_attribute(p, value)

    return 0


@app.get("/api/get/{path:path}")
async def get_param(path: str):
    """GET /api/get/<path> - Retrieve a value or list indexable children.

    If the value at *path* is a scalar, returns it directly.
    If it is a container, returns the keys/indices one level deep.

    :param path: slash-separated config path.
    """
    global musician

    if not musician:
        raise HTTPException(status_code=400, detail="LOERIC is not running")

    value = _get_param(path)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Path '{path}' not found")

    return value


def _get_param(path: str):
    global musician

    value = musician.get_attribute(path)

    if value is None:
        return None

    if isinstance(value, (int, float, str, bool)):
        return {"path": path, "value": value}

    if isinstance(value, dict):
        return {"path": path, "children": list(value.keys())}

    if isinstance(value, (list, tuple)):
        return {"path": path, "children": list(range(len(value)))}

    # object: return exposed properties
    children = [
        name
        for name in dir(type(value))
        if isinstance(getattr(type(value), name, None), property)
    ]
    return {"path": path, "children": children}


@app.post("/api/change/{path:path}")
async def change_param(path: str, value: str):
    """POST /api/change/<anything>?value=..."""

    global musician

    if not musician:
        raise HTTPException(status_code=400, detail="LOERIC is not running")

    musician.set_attribute(path, value)

    return await get_status()


@app.post("/api/start")
async def start(request: lsm.StartRequest):
    """POST /api/start - Start loeric with specified tune and parameters."""
    if state.running:
        raise HTTPException(status_code=400, detail="LOERIC is already running")

    try:
        await start_loeric(
            tune=request.tune,
            repetitions=request.repetitions,
            transpose=request.transpose,
            config=request.config,
            instrument_model=request.instrument_model,
            tempo=request.tempo,
            responsiveness=request.responsiveness,
            volume=request.volume,
        )
        return {
            "status": "started",
            "tune": request.tune,
            "repetitions": request.repetitions,
            "transpose": request.transpose,
            "config": request.config,
            "instrument": request.instrument_model,
            "tempo": request.tempo,
            "responsiveness": request.responsiveness,
            "volume": request.volume,
        }
    except Exception as e:
        logger.error(f"Start failed: {e}")
        raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stop")
async def stop():
    """POST /api/stop - Stop the running loeric process."""
    if not state.running:
        raise HTTPException(status_code=400, detail="LOERIC is not running")

    try:
        await stop_loeric()
        return {"status": "stopped"}
    except Exception as e:
        logger.error(f"Stop failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status", response_model=lsm.StatusResponse)
async def get_status():
    """GET /api/status - Get current loeric status."""
    return lsm.StatusResponse(
        running=state.running,
        current_tune=state.current_tune,
        current_config=state.current_config,
        current_instrument=state.parameters.get("instrument"),
        parameters=state.parameters,
    )


# ============================================================================
# Static Files & Index
# ============================================================================


# TODO change this behaviour
@app.get("/")
async def index():
    """Serve the main GUI."""
    if not GUI_FILE.exists():
        logger.warning(f"GUI file not found at {GUI_FILE}, serving loeric-gui.html")
        return FileResponse("loeric-gui.html")
    return FileResponse(GUI_FILE)


def main():
    """Start the server."""
    global BASE_CONFIG

    import argparse

    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--device",
        help="Load device-specific configs (options: ['mandaloeric']).",
        type=str,
        default=None,
    )
    args = parser.parse_args()

    if args.device is not None:
        BASE_CONFIG = Path(CONFIG_PATH / f"{args.device}_base.json")

    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
