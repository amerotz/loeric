"""FastAPI server for Loeric GUI.

Serves the static HTML interface and provides API endpoints to control loeric
"""

import json
import logging
import multiprocessing
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
process = None
musician = None
shutdown_event = multiprocessing.Event()


def process_monitor():
    global process

    while True:
        if process is not None and process.is_alive():
            process.join()

            process = None
            state.running = False
            state.current_tune = None
            state.current_config = None

        time.sleep(0.5)


threading.Thread(
    target=process_monitor,
    daemon=True,
).start()


if getattr(sys, "frozen", False):
    print("Running compiled binary.")
    BASE_DIR = Path(sys._MEIPASS)
else:
    print("Running from cli.")
    BASE_DIR = Path(__file__).resolve().parents[3]

STATIC_ROOT = Path(os.getenv("LOERIC_WEBAPP_DIR", BASE_DIR / "static")).resolve()

# Configuration
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

# create loeric
with open(BASE_CONFIG, "r") as f:
    base_config = json.load(f)
    musician = loeric.LOERIC(config=base_config)
    del base_config

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

    Returns a tuple of (default_config, all_configs)
    """
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
    instruments = [
        lsm.InstrumentModel(id="piano", name="Piano"),
        lsm.InstrumentModel(id="violin", name="Violin"),
        lsm.InstrumentModel(id="flute", name="Flute"),
        lsm.InstrumentModel(id="guitar", name="Guitar"),
        lsm.InstrumentModel(id="synth", name="Synthesizer"),
    ]
    return instruments


def _run_loeric(config, tune_path, tempo, stop_event):
    musician = None

    try:
        tune = tu.Tune(tune_path, 1)

        musician = loeric.LOERIC(config=config)
        musician.set_tune(tune)
        musician.set_tempo(tempo)

        musician.ready()
        musician.start(stop_event)

    finally:
        if musician:
            musician.reset()


async def start_loeric(
    tune: str, config: str, instrument_model: str, tempo: int
) -> bool:
    """Start loeric with the specified tune and parameters.

    ADAPT THIS TO YOUR LOERIC SETUP:
    - Replace command with appropriate loeric invocation
    - Adjust parameter names/format to match loeric's CLI
    - Handle environment setup if needed
    """
    global process
    try:

        # Update state
        state.current_tune = tune
        state.current_config = config
        state.parameters = {
            "tempo": tempo,
            "instrument": instrument_model,
        }

        with open(CONFIG_PATH / state.current_config, "r") as f:
            config = json.load(f)
            config = lc.process_config(config)

        shutdown_event.clear()

        process = multiprocessing.Process(
            target=_run_loeric,
            daemon=True,
            args=(
                config,
                tune_list[state.current_tune].path,
                state.parameters["tempo"],
                shutdown_event,
            ),
        )
        process.start()

        state.running = True

        return True

    except Exception as e:
        logger.error(f"Failed to start loeric: {e}")
        raise e


async def stop_loeric() -> bool:
    """Stop the running loeric process."""
    global process
    try:
        # TODO: Implement actual process termination
        logger.info("Stopping loeric")

        shutdown_event.set()

        if process:
            process.join(timeout=1)

            if process.is_alive():
                logger.warning("Graceful shutdown timed out, terminating")
                process.terminate()
                process.join()

        process = None

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
    """GET /api/tunes - Get list of available tunes"""
    return lsm.TunesResponse(tunes=list(tune_list.values()))


@app.get("/api/configs/{tune_id}", response_model=lsm.ConfigsResponse)
async def get_configs(tune_id: str):
    """GET /api/configs/{tune_id} - Get available configurations for a tune.

    Returns the default config and list of all available configs.
    """
    default_config, configs = get_available_configs(tune_id)

    if default_config is None:
        raise HTTPException(
            status_code=404, detail=f"No configurations found for tune: {tune_id}"
        )

    return lsm.ConfigsResponse(default_config=default_config, configs=configs)


@app.get("/api/instruments", response_model=lsm.InstrumentModelsResponse)
async def get_instruments():
    """GET /api/instruments - Get available instrument models"""
    instruments = get_available_instruments()
    return lsm.InstrumentModelsResponse(models=instruments)


@app.post("/api/start")
async def start(request: lsm.StartRequest):
    """POST /api/start - Start loeric with specified tune and parameters"""
    if state.running:
        raise HTTPException(status_code=400, detail="LOERIC is already running")

    try:
        await start_loeric(
            tune=request.tune,
            config=request.config,
            instrument_model=request.instrument_model,
            tempo=request.tempo,
        )
        return {
            "status": "started",
            "tune": request.tune,
            "config": request.config,
            "instrument": request.instrument_model,
            "tempo": request.tempo,
        }
    except Exception as e:
        logger.error(f"Start failed: {e}")
        raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/stop")
async def stop():
    """POST /api/stop - Stop the running loeric process"""
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
    """GET /api/status - Get current loeric status"""
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


@app.get("/")
async def index():
    """Serve the main GUI"""
    if not GUI_FILE.exists():
        logger.warning(f"GUI file not found at {GUI_FILE}, serving loeric-gui.html")
        return FileResponse("loeric-gui.html")
    return FileResponse(GUI_FILE)


# Run with: uvicorn main:app --host 0.0.0.0 --port 8000
def main():
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
