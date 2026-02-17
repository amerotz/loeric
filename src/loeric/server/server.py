import json
import os
import sys
from pathlib import Path
from typing import List

import mido
import nanoid as nid
import pyaudio as pa
import tinysoundfont
from bottle import Bottle, HTTPResponse, request, response, run, static_file
from muspy.outputs.midi import PITCH_NAMES

import loeric.loeric_utils as lu
import loeric.server.musician as lsm
import loeric.server.synthout as lss
import loeric.tune as tu


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parents[3]

STATIC_ROOT = Path(os.getenv("LOERIC_WEBAPP_DIR", BASE_DIR / "static")).resolve()

TRACK_DIR = STATIC_ROOT / "midi"
TEMP_DIR = STATIC_ROOT / "temp"
SPECIFIC_CONFIGS_PATH = STATIC_ROOT / "webapp_configs"
SOUND_ROOT = STATIC_ROOT / "sound"
FRONTEND_ROOT = STATIC_ROOT / "site"

"""
# track_dir = os.path.join(os.getcwd(), "static/midi")
track_dir = Path(__file__).resolve().parent / "static" / "midi"
sound_dir = Path(__file__).resolve().parent / "static" / "sound"
# specific_configs_path = os.path.join(os.getcwd(), "static/webapp_configs")
specific_configs_path = Path(__file__).resolve().parent / "static" / "webapp_configs"
"""

app = Bottle()

musicians: list[lsm.Musician] = []
names = ["LOERIC"]

synth = None  # , tinysoundfont.Synth()
synth_is_running = False
soundfonts = []


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
    return sorted(
        [
            f
            for f in os.listdir(TRACK_DIR)
            if os.path.isfile(TRACK_DIR / f)
            and os.path.splitext(f)[1].casefold() in filetypes
            and not f.startswith(".")
        ]
    )


def _list_custom_tracks() -> List[str]:
    configs = os.listdir(SPECIFIC_CONFIGS_PATH / "tunes")
    return [f for f in _list_tracks() if f.split(".")[0] + ".json" in configs]


@app.get("/api/state")
def _state():
    response.set_header("Access-Control-Allow-Origin", "*")
    return {
        "musicians": [m.__json__() for m in musicians],
        "playing": _is_playing(),  # lsm.get__state().name,
        "track": {
            "name": current_track,
            "type": current_track.split(".")[-1],
            "time": f"{musicians[0].tune.time_signature.numerator}/{musicians[0].tune.time_signature.denominator}",
            "config": musicians[0].tune.get_config(),
            "key": _key_to_str(musicians[0].tune.key_signature),
            "tempo": musicians[0].groover.tempo.qpm,
            "repeats": musicians[0].tune.repeats,
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
def _play():
    """
    if lsm.get__state() == lsm.State.STOPPED:
        for index, musician in enumerate(musicians):
            if musician.midi_out is None or isinstance(
                musician.midi_out, lss.SynthOutput
            ):
                synth.program_select(
                    musician.groover._midi_channel,
                    soundfonts[musician.instrument].soundfont_id,
                    0,
                    soundfonts[musician.instrument].program,
                )
                if musician.midi_out is None:
                    musician.midi_out = lss.SynthOutput(
                        f"LOERIC out #{musician.id}#", synth, index
                    )
                else:
                    musician.midi_out.channel = index
            musician.ready()
        _start_synth()
    if lsm.get__state() == lsm.State.PAUSED:
        for musician in musicians:
            musician.unpause()

    lsm.update_state(lsm.State.PLAYING)
    """
    _start_synth()
    for musician in musicians:
        musician.start()
    return _state()


@app.get("/api/pause")
def _pause():
    _stop_synth()
    for musician in musicians:
        musician.pause()
    """
    lsm.update_state(lsm.State.PAUSED)
    for musician in musicians:
        musician.pause()
    """
    return _state()


@app.get("/api/stop")
def _stop():
    _stop_synth()
    for musician in musicians:
        musician.stop()

    """
    lsm.update_state(lsm.State.STOPPED)
    for musician in musicians:
        musician.stop()
        # musician.create_all()
    lsm.update_state(lsm.State.STOPPED)
    """
    return _state()


@app.put("/api/instrument")
def _instrument_change():
    _stop()
    musician_id = request.forms.id
    new_instrument = request.forms.instrument

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

    return _state()


@app.put("/api/control")
def _control_change():
    musician_id = request.forms.id
    control = int(request.forms.control)
    new_value = float(request.forms.value)

    for musician in musicians:
        if musician.id == musician_id:
            musician.set_control_value(control, new_value)

    return _state()


@app.put("/api/output")
def _output_change():
    musician_id = request.forms.id
    new_output = request.forms.output

    for index, musician in enumerate(musicians):
        if musician.id == musician_id:

            _stop_synth()

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

    return _state()


@app.put("/api/input")
def _input_change():
    musician_id = request.forms.id
    new_input = request.forms.input

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
            musician.stop_threads()
            musician.midi_in = midi_input
            musician.set_input_audio_device(device_index)

    return _state()


@app.put("/api/tempo")
def _set_tempo():
    global tempo
    tempo = int(request.forms.tempo)
    for musician in musicians:
        musician.set_tempo(tempo)

    return _state()


@app.put("/api/drones")
def _set_drones():
    value = request.forms.drones == "true"
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.groover.set_droning(value)

    return _state()


@app.put("/api/slow_start")
def _set_slow_start():
    _stop()
    value = request.forms.slow_start == "true"
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.slow_start = value

    return _state()


@app.put("/api/slow_end")
def _set_slow_end():
    _stop()
    value = request.forms.slow_end == "true"
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.slow_end = value

    return _state()


@app.put("/api/transpose")
def _set_transpose():
    value = int(request.forms.transpose)
    print(value)
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.set_transpose(value)

    return _state()


@app.put("/api/repeat")
def _set_repeat():
    global repetitions
    _stop()
    repetitions = int(request.forms.repeats)
    __set_track(current_track)

    return _state()


@app.put("/api/audio_out")
def _set_audio_out():
    global audio_device_index

    _stop_synth()
    audio_device_index = int(request.forms.device.split(":")[-1])
    _start_synth()

    return _state()


@app.put("/api/track")
def _set_track():
    _stop()
    track = request.forms.track
    __set_track(track)
    return _state()


@app.get("/api/track")
def _get_track():
    return _state()


@app.error(405)
def _method_not_allowed(res):
    if request.method == "OPTIONS":
        new_res = HTTPResponse()
        new_res.set_header("Access-Control-Allow-Methods", "POST, PUT, GET, OPTIONS")
        new_res.set_header("Access-Control-Allow-Origin", "*")
        return new_res
    res.headers["Allow"] += ", OPTIONS"
    return request.app.default_error_handler(res)


"""
@app.post("/api/musician/config")
def upload_musician_config():
    global musicians
    musician_id = request.forms.id
    for index, musician in enumerate(musicians):
        if musician.id == musician_id:
            upload = request.files.get("upload")
            filename = f"musician/{musician.name}"
            path = webapp_config_path(filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            upload.save(path, overwrite=True)

            musician.config = webapp_load_config(filename)

    return _state()


@app.post("/api/track/config")
def upload_track_config():
    global tune
    upload = request.files.get("upload")
    filename = f"tunes/{os.path.splitext(tune.name.lower())[0]}"
    path = webapp_config_path(filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    upload.save(path, overwrite=True)

    tune.config = webapp_load_config(filename)

    return _state()
"""


@app.post("/api/track")
def _upload_track():
    upload = request.files.get("upload")
    file = TRACK_DIR / upload.filename
    upload.save(file)

    return _state()


"""
@app.get("/")
def get_static():
    return static_file("/index.html", root="static/site")


@app.get("/<filepath:path>")
def get_static_filepath(filepath):
    return static_file(filepath, root="static/site")
"""


@app.get("/")
def _get_static():
    return static_file("index.html", root=str(FRONTEND_ROOT))


@app.get("/<filepath:path>")
def _get_static_filepath(filepath):
    return static_file(filepath, root=str(FRONTEND_ROOT))


@app.get("/favicon.ico")
def _favicon():
    path = FRONTEND_ROOT / "favicon.ico"
    if path.exists():
        return static_file("favicon.ico", root=str(FRONTEND_ROOT))
    return "", 204


@app.get("/api/add_musician")
def _add_musician_api():
    _add_musician()
    return _state()


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

    run(app, host="localhost", port=8080, quiet=True)
    _stop_synth()
