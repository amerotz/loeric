import asyncio
import json
import os
import sys
import threading
import time
import webbrowser
from collections import defaultdict
from pathlib import Path
from typing import List

# from bottle import Bottle, HTTPResponse, request, response, run, static_file
import fastapi as fapi
import mido
import nanoid as nid
import pyaudio as pa
import tinysoundfont
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from muspy.outputs.midi import PITCH_NAMES

import loeric.loeric_utils as lu
import loeric.server.musician as lsm
import loeric.server.synthout as lss
import loeric.tune as tu


PORT = int(os.getenv("LOERIC_WEBAPP_PORT", 8080))

if getattr(sys, "frozen", False):
    print("Running compiled binary.")
    BASE_DIR = Path(sys._MEIPASS)
else:
    print("Running from cli.")
    BASE_DIR = Path(__file__).resolve().parents[3]

STATIC_ROOT = Path(os.getenv("LOERIC_WEBAPP_DIR", BASE_DIR / "static")).resolve()

TRACK_DIR = STATIC_ROOT / "midi"
TEMP_DIR = STATIC_ROOT / "temp"
SPECIFIC_CONFIGS_PATH = STATIC_ROOT / "webapp_configs"
SOUND_ROOT = STATIC_ROOT / "sound"
FRONTEND_ROOT = STATIC_ROOT / "site"

_last_heartbeat = time.time()
HEARTBEAT_TIMEOUT = 10  # seconds

# app = Bottle()
app = fapi.FastAPI()
connections: dict[str, set[fapi.WebSocket]] = defaultdict(set)
main_loop = asyncio.get_event_loop()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to your frontend
    allow_methods=["*"],
    allow_headers=["*"],
)

musicians: list[lsm.Musician] = []
names = ["LOERIC"]

synth = None  # , tinysoundfont.Synth()
synth_is_running = False
soundfonts = []


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: fapi.WebSocket, client_id: str):
    await websocket.accept()

    for musician in musicians:
        if musician.id == client_id:
            # Add client to the ID group
            musician.connected_clients.add(websocket)

            print(f"Client connected with ID: {client_id}")
            try:
                while True:
                    # Optional: receive messages
                    msg = await websocket.receive_text()
                    print(f"Received from {client_id}: {msg}")
            except fapi.WebSocketDisconnect:
                print(f"Client {client_id} disconnected")
                musician.connected_clients.remove(websocket)


def _monitor_browser():
    while True:
        time.sleep(3)
        if time.time() - _last_heartbeat > HEARTBEAT_TIMEOUT:
            print("Browser closed. Shutting down LOERIC...")
            os._exit(0)


@app.post("/api/heartbeat")
def _heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()
    return {"status": "alive"}


def _is_playing():
    playing = False
    for musician in musicians:
        # print(musician.playing)
        playing = playing or musician.playing
    return playing


def _load_soundfonts():
    global soundfonts

    # Absolute paths
    default_soundfont_id = synth.sfload(str(SOUND_ROOT / "FluidR3_GM.sf2"))

    soundfonts = {
        "Accordion": lss.SynthSound(
            name="Accordion",
            path=str(SOUND_ROOT / "Diato.sf2"),
            program=1,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/accordion.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=21,
            default_config=str(lu.general_configs_path / "instrument/accordion.json"),
        ),
        "Guitar": lss.SynthSound(
            name="Guitar",
            path=str(SOUND_ROOT / "guitar.sf2"),
            program=3,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/guitar.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=25,
            default_config=str(lu.general_configs_path / "instrument/guitar.json"),
        ),
        "Piano": lss.SynthSound(
            name="Piano",
            path=str(SOUND_ROOT / "piano.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=0,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            gain=-10,
        ),
        "Piano (Comping)": lss.SynthSound(
            name="Piano (Comping)",
            path=str(SOUND_ROOT / "piano.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano_comping.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=0,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano_comping.json"),
            gain=-10,
        ),
        "Harp": lss.SynthSound(
            name="Harp",
            path=str(SOUND_ROOT / "Celtic Harp.sf2"),
            program=46,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/harp.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=46,
            default_config=str(lu.general_configs_path / "instrument/harp.json"),
        ),
        "Flute": lss.SynthSound(
            name="Flute",
            path=str(SOUND_ROOT / "FLUTE2.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/flute.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=73,
            default_config=str(lu.general_configs_path / "instrument/flute.json"),
        ),
        "Violin": lss.SynthSound(
            name="Violin",
            path=str(SOUND_ROOT / "violin.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/violin.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=40,
            default_config=str(lu.general_configs_path / "instrument/violin.json"),
        ),
        "Saw": lss.SynthSound(
            name="Saw",
            path=str(SOUND_ROOT / "saw.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=81,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
        ),
        "Square": lss.SynthSound(
            name="Square",
            path=str(SOUND_ROOT / "saw.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=80,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
        ),
        "Polysynth": lss.SynthSound(
            name="Polysynth",
            path=str(SOUND_ROOT / "saw.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=90,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
        ),
        "Fantasia": lss.SynthSound(
            name="Fantasia",
            path=str(SOUND_ROOT / "saw.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=88,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
        ),
        "Vox": lss.SynthSound(
            name="Vox",
            path=str(SOUND_ROOT / "saw.sf2"),
            program=0,
            config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
            default_soundfont_id=default_soundfont_id,
            default_program=85,
            default_config=str(SPECIFIC_CONFIGS_PATH / "instrument/piano.json"),
        ),
    }

    # Load all soundfonts into the synth
    for sound in soundfonts.values():
        sound.load(synth)


audio_device_index = 0
tempo = 160
repetitions = 2
current_track = None
filetypes = [".mid", ".abc", ".set"]


def _list_audio_inputs():
    audio = pa.PyAudio()
    audio_list = {}

    for i in range(0, audio.get_device_count()):
        if (audio.get_device_info_by_index(i).get("maxInputChannels")) > 0:
            name = audio.get_device_info_by_index(i).get("name")
            audio_list[name] = i

    return audio_list


def _list_audio_outputs():
    audio = pa.PyAudio()

    audio_list = {}

    for i in range(0, audio.get_device_count()):
        if (audio.get_device_info_by_index(i).get("maxOutputChannels")) > 0:
            name = audio.get_device_info_by_index(i).get("name")
            audio_list[name] = i

    return audio_list


def _start_synth():
    global synth_is_running
    if not synth_is_running:
        audio = pa.PyAudio()
        info = audio.get_device_info_by_index(audio_device_index)
        print(info)
        synth.start(
            output_device_index=audio_device_index,
        )
        synth_is_running = True


def _stop_synth():
    global synth_is_running
    if synth_is_running:
        synth.stop()
        synth_is_running = False


def _key_to_str(key) -> str:
    return f"{PITCH_NAMES[key.root]} {key.mode}"


def _list_tracks() -> List[str]:
    t_list = [
        f
        for f in os.listdir(TRACK_DIR)
        if os.path.isfile(TRACK_DIR / f)
        and os.path.splitext(f)[1].casefold() in filetypes
        and not f.startswith(".")
    ]
    t_list.sort(key=lambda x: (int(x.split(".")[-1] != "set"), x))
    return t_list


def _list_custom_tracks() -> List[str]:
    configs = os.listdir(SPECIFIC_CONFIGS_PATH / "tunes")
    return [f for f in _list_tracks() if f.split(".")[0] + ".json" in configs]


@app.get("/api/state")
async def _state():
    # response.set_header("Access-Control-Allow-Origin", "*")
    return {
        "musicians": [m.__json__() for m in musicians],
        "playing": _is_playing(),  # lsm.get__state().name,
        "track": {
            "name": current_track,
            "type": current_track.split(".")[-1],
            "time": f"{musicians[0].current_tune.time_signature.numerator}/{musicians[0].current_tune.time_signature.denominator}",
            # "config": musicians[0].current_groover._config,
            "key": _key_to_str(musicians[0].current_tune.key_signature),
            "tempo": musicians[0].current_groover.tempo.qpm,
            "repeats": musicians[0].current_tune.repeats,
        },
        "options": {
            "inputs": mido.get_input_names(),
            "outputs": mido.get_output_names(),
            "instruments": list(soundfonts.keys()),
            "trackList": _list_tracks(),
            "customized_tracks": _list_custom_tracks(),
            "audio_inputs": _list_audio_inputs(),
            "audio_outputs": _list_audio_outputs(),
            "selected_audio_out": audio_device_index,
        },
    }


@app.get("/api/controls")
def _controls():
    response.set_header("Access-Control-Allow-Origin", "*")
    return {
        "playing": _is_playing(),
        "intensity": {m.id: m.input_intensity for m in musicians},
    }


def __set_track(track: str):
    global current_track

    current_track = track
    track_list = _list_tracks()

    if track in track_list:

        tunes = []
        if os.path.splitext(track)[1] == ".set":

            with open(TRACK_DIR / track, "r") as f:
                set_config = json.load(f)

            for t in set_config:
                tune_config = (
                    SPECIFIC_CONFIGS_PATH
                    / "tunes"
                    / f"{os.path.splitext(t["file"])[0]}.json"
                )
                if t["config"] is not None:
                    tune_config = t["config"]

                tune_qpm = tempo
                if t["qpm"] is not None:
                    tune_qpm = t["qpm"]

                tunes.append(
                    (
                        t["file"],
                        t["repetitions"],
                        tune_config,
                        t["trim_end_eighths"],
                        tune_qpm,
                    )
                )

        else:
            tunes.append(
                (
                    track,
                    repetitions,
                    SPECIFIC_CONFIGS_PATH
                    / "tunes"
                    / f"{os.path.splitext(track)[0]}.json",
                    0,
                    tempo,
                )
            )

        for musician in musicians:
            musician._tunes = []
            musician._tempos = []

        for name, repeats, config, trim, qpm in tunes:
            tune = tu.Tune(
                filename=str(TRACK_DIR / name),
                repeats=repeats,
                config=config,
                trim_end_eighths=trim,
            )

            for musician in musicians:
                musician._tunes.append(tune)
                musician._tempos.append(qpm)

        for musician in musicians:
            musician.create_all()


@app.get("/api/play")
async def _play():
    _start_synth()
    for musician in musicians:
        musician.start()
    return await _state()


@app.get("/api/pause")
async def _pause():
    _stop_synth()
    for musician in musicians:
        musician.pause()
    return await _state()


def __stop():
    _stop_synth()
    for musician in musicians:
        musician.stop()


@app.get("/api/stop")
async def _stop():
    _stop_synth()
    for musician in musicians:
        musician.stop()

    return await _state()


@app.put("/api/instrument")
async def _instrument_change(request: fapi.Request):
    __stop()
    form = await request.form()
    musician_id = form["id"]
    new_instrument = form["instrument"]

    for musician in musicians:
        if musician.id == musician_id:
            musician.instrument = soundfonts[new_instrument]
            for channel in musician.midi_channels:

                synth.program_select(
                    channel,
                    soundfonts[musician.instrument].soundfont_id,
                    0,
                    soundfonts[musician.instrument].program,
                )

    return await _state()


@app.put("/api/control")
async def _control_change(request: fapi.Request):
    form = await request.form()
    musician_id = form["id"]
    control = int(form["control"])
    new_value = float(form["value"])

    for musician in musicians:
        if musician.id == musician_id:
            musician.set_control_value(control, new_value)

    return await _state()


@app.put("/api/output")
async def _output_change(request: fapi.Request):
    form = await request.form()
    musician_id = form["id"]
    new_output = form["output"]

    for index, musician in enumerate(musicians):
        if musician.id == musician_id:

            _stop_synth()
            musician.midi_out.reset()

            if new_output == "create_out":
                midi_output = mido.open_output(
                    f"LOERIC out #{musician.id}#", virtual=True
                )
            elif new_output == "synth":
                midi_output = lss.SynthOutput(f"LOERIC Synth {musician.id}", synth)
                _start_synth()
            else:
                midi_output = mido.open_output(new_output)

            musician.midi_out = midi_output

    return await _state()


@app.put("/api/input")
async def _input_change(request: fapi.Request):
    form = await request.form()
    musician_id = form["id"]
    new_input = form["input"]

    # assume it's no input
    device_index = None
    midi_input = None
    # if it is audio input
    if new_input.startswith("audioIn"):
        device_index = int(new_input.split(":")[-1])
    # if it is midi input
    elif new_input != "no_in":
        midi_input = mido.open_input(new_input)

    for musician in musicians:
        if musician.id == musician_id:
            musician.midi_in = midi_input
            musician.set_input_audio_device(device_index)

    return await _state()


@app.put("/api/tempo")
async def _set_tempo(request: fapi.Request):
    global tempo
    form = await request.form()
    tempo = int(form["tempo"])
    for musician in musicians:
        musician.set_tempo(tempo)

    return await _state()


@app.put("/api/drones")
async def _set_drones(request: fapi.Request):
    form = await request.form()
    value = form["drones"] == "true"
    musician_id = form["id"]
    for musician in musicians:
        if musician.id == musician_id:
            musician.current_groover.set_droning(value)

    return await _state()


@app.put("/api/invert")
async def _set_invert(request: fapi.Request):
    form = await request.form()
    value = form["invert"] == "true"
    musician_id = form["id"]
    for musician in musicians:
        if musician.id == musician_id:
            musician.invert = value

    return await _state()


@app.put("/api/slow_start")
async def _set_slow_start(request: fapi.Request):
    __stop()
    form = await request.form()
    value = form["slow_start"] == "true"
    musician_id = form["id"]
    for musician in musicians:
        if musician.id == musician_id:
            musician.slow_start = value

    return await _state()


@app.put("/api/slow_end")
async def _set_slow_end(request: fapi.Request):
    __stop()
    form = await request.form()
    value = form["slow_end"] == "true"
    musician_id = form["id"]
    for musician in musicians:
        if musician.id == musician_id:
            musician.slow_end = value

    return await _state()


@app.put("/api/transpose")
async def _set_transpose(request: fapi.Request):
    form = await request.form()
    value = int(form["transpose"])
    print(value)
    musician_id = form["id"]
    for musician in musicians:
        if musician.id == musician_id:
            musician.set_transpose(value)

    return await _state()


@app.put("/api/repeat")
async def _set_repeat(request: fapi.Request):
    global repetitions
    __stop()
    form = await request.form()
    repetitions = int(form["repeats"])
    __set_track(current_track)

    return await _state()


@app.put("/api/audio_out")
async def _set_audio_out(request: fapi.Request):
    global audio_device_index

    form = await request.form()
    _stop_synth()
    audio_device_index = int(form["device"].split(":")[-1])
    _start_synth()

    return await _state()


@app.put("/api/track")
async def _set_track(request: fapi.Request):
    __stop()
    form = await request.form()
    track = form["track"]
    __set_track(track)
    return await _state()


@app.get("/api/track")
async def _get_track():
    return await _state()


"""
@app.error(405)
async def _method_not_allowed(res):
    if request.method == "OPTIONS":
        new_res = HTTPResponse()
        new_res.set_header("Access-Control-Allow-Methods", "POST, PUT, GET, OPTIONS")
        new_res.set_header("Access-Control-Allow-Origin", "*")
        return new_res
    res.headers["Allow"] += ", OPTIONS"
    return request.app.default_error_handler(res)
"""


"""
@app.post("/api/musician/config")
def upload_musician_config():
    global musicians
    form = await request.form()
    musician_id = form["id"]
    for index, musician in enumerate(musicians):
        if musician.id == musician_id:
            upload = request.files.get("upload")
            filename = f"musician/{musician.name}"
            path = webapp_config_path(filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            upload.save(path, overwrite=True)

            musician.config = webapp_load_config(filename)

    return await _state()


@app.post("/api/track/config")
def upload_track_config():
    global tune
    upload = request.files.get("upload")
    filename = f"tunes/{os.path.splitext(tune.name.lower())[0]}"
    path = webapp_config_path(filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    upload.save(path, overwrite=True)

    tune.config = webapp_load_config(filename)

    return await _state()
"""


@app.post("/api/track")
async def _upload_track(request: fapi.Request):
    upload = request.files.get("upload")
    file = TRACK_DIR / upload.filename
    upload.save(file)

    return await _state()


"""
@app.get("/")
def get_static():
    return static_file("/index.html", root="static/site")


@app.get("/<filepath:path>")
def get_static_filepath(filepath):
    return static_file(filepath, root="static/site")


@app.get("/")
def _get_static():
    return static_file("index.html", root=str(FRONTEND_ROOT))


@app.get("/<filepath:path>")
def _get_static_filepath(filepath):
    return static_file(filepath, root=str(FRONTEND_ROOT))
"""


@app.get("/api/add_musician")
async def _add_musician_api():
    __stop()
    _add_musician()
    __set_track(current_track)
    return await _state()


def _add_musician():
    loeric_id = nid.generate(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10
    )
    existing = [m.name for m in musicians]
    unused = list(set(names) - set(existing))
    instrument_key = next(iter(soundfonts))
    musician = lsm.Musician(
        name=unused[0],
        loeric_id=loeric_id,
        synth_sound=soundfonts[instrument_key],
        midi_out=lss.SynthOutput(f"LOERIC Synth {loeric_id}", synth),
    )
    musicians.append(musician)


def _init_musician(track):
    _add_musician()

    __set_track(track)

    musician = musicians[0]

    for channel in musician.midi_channels:
        synth.program_select(
            channel,
            soundfonts[musician.instrument].soundfont_id,
            0,
            soundfonts[musician.instrument].program,
        )

    _start_synth()


def _open_browser():
    # Wait a bit to ensure server is ready
    time.sleep(1)
    webbrowser.open(f"http://localhost:{PORT}")


def start_server():
    """Start the server by loading soundfonts, opening audio devices and initialising a musician."""
    global audio_device_index, synth

    synth = tinysoundfont.Synth()
    _load_soundfonts()

    audio_device_index = pa.PyAudio().get_default_output_device_info()["index"]
    track_list = _list_tracks()
    if len(track_list) > 0:
        track = track_list[0]
        _init_musician(track)

    if getattr(sys, "frozen", False):
        threading.Thread(target=_open_browser, daemon=True).start()

    threading.Thread(target=_monitor_browser, daemon=True).start()

    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_ROOT), html=True),
        name="static",
    )
    # run(app, host="localhost", port=PORT, quiet=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT)
    _stop_synth()
