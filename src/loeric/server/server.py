import os
import mido
import tinysoundfont
import pyaudio as pa

from typing import List
from bottle import Bottle, run, static_file, request, response, HTTPResponse, abort
from muspy.outputs.midi import PITCH_NAMES
from nanoid import generate
from random import shuffle

from loeric.server.musician import (
    Musician,
    get_state,
    play_all,
    stop_all,
    pause_all,
    State,
)
from loeric.server.synthout import SynthOutput
from loeric.tune import Tune

track_dir = os.path.join(os.getcwd(), "static/midi")
temp_dir = os.path.join(os.getcwd(), "static/temp")
general_configs_path = os.getcwd() + "/src/loeric/loeric_config/performance"
specific_configs_path = os.getcwd() + "/src/loeric/loeric_config/webapp_configs"

app = Bottle()

tune: Tune
musicians: list[Musician] = []
names = ["LOERIC"]
shuffle(names)

synth = tinysoundfont.Synth()
synth_is_running = False
instruments = {
    "Accordion": 1,
    "Guitar": 25,
    "Piano": 0,
    "Harp": 46,
    "Flute": 0,
    "Violin": 40,
}

default_soundfont_id = 0
soundfonts = {}


def load_soundfont(path, gain=0):
    global default_soundfont_id
    if not os.path.isfile(path):
        return default_soundfont_id
    return synth.sfload(path, gain=gain)


def load_synths():
    global soundfonts, default_soundfont_id
    default_soundfont_id = synth.sfload("static/sound/FluidR3_GM.sf2")
    soundfonts = {
        "Accordion": load_soundfont("static/sound/accordion.sf2"),
        "Guitar": load_soundfont("static/sound/MusicLab_Acoustic_Guitars.sf2"),
        "Harp": load_soundfont("static/sound/Celtic Harp.sf2", gain=-10),
        "Flute": load_soundfont("static/sound/FLUTE2.sf2"),
        "Violin": default_soundfont_id,
        "Piano": load_soundfont("static/sound/piano.sf2"),
    }


audio_device_index = 0
tempo = 140
repetitions = 2
current_track = None
filetypes = [".mid", ".abc"]


def list_audio_inputs():
    audio = pa.PyAudio()
    audio_list = {}

    for i in range(0, audio.get_device_count()):
        if (audio.get_device_info_by_index(i).get("maxInputChannels")) > 0:
            name = audio.get_device_info_by_index(i).get("name")
            audio_list[name] = i

    return audio_list


def list_audio_outputs():
    audio = pa.PyAudio()

    audio_list = {}

    for i in range(0, audio.get_device_count()):
        if (audio.get_device_info_by_index(i).get("maxOutputChannels")) > 0:
            name = audio.get_device_info_by_index(i).get("name")
            audio_list[name] = i

    return audio_list


def start_synth():
    global audio_device_index, synth_is_running, synth
    if not synth_is_running:
        audio = pa.PyAudio()
        info = audio.get_device_info_by_index(audio_device_index)
        print(info)
        synth.start(
            output_device_index=audio_device_index,
        )
        synth_is_running = True


def stop_synth():
    global synth_is_running, synth
    if synth_is_running:
        synth.stop()
        synth_is_running = False


def key_to_str(key) -> str:
    return f"{PITCH_NAMES[key.root]} {key.mode}"


def trim_ext(file: str) -> str:
    return os.path.splitext(file)[0]


def list_tracks() -> List[str]:
    return [
        f
        for f in os.listdir(track_dir)
        if os.path.isfile(os.path.join(track_dir, f))
        and os.path.splitext(f)[1].casefold() in filetypes
    ]


@app.get("/api/state")
def state():
    global tune, tempo, repetitions
    response.set_header("Access-Control-Allow-Origin", "*")
    return {
        "musicians": list(map(lambda m: m.__json__(), musicians)),
        "state": get_state().name,
        "track": {
            "name": os.path.basename(tune._filename),
            "time": f"{tune.time_signature.numerator}/{tune.time_signature.denominator}",
            "config": tune.get_config(),
            "key": key_to_str(tune.key_signature),
            "tempo": tempo,
            "repeats": repetitions,
        },
        "options": {
            "inputs": mido.get_input_names(),
            "outputs": mido.get_output_names(),
            "instruments": list(instruments.keys()),
            "trackList": list_tracks(),
            "audio_inputs": list_audio_inputs(),
            "audio_outputs": list_audio_outputs(),
            "selected_audio_out": audio_device_index,
        },
    }


def __set_track(track: str):
    global tune, repetitions, current_track

    current_track = track
    track_list = list_tracks()
    if track in track_list:

        name = os.path.splitext(track.lower().replace("'", "").replace(" ", ""))[0]
        tune = Tune(
            os.path.join(track_dir, track),
            repeats=repetitions,
            config=f"{specific_configs_path}/tunes/{name}.json",
        )

        for musician in musicians:
            musician.tune = tune


@app.get("/api/play")
def play():
    global synth_is_running, musicians
    for index, musician in enumerate(musicians):
        if musician.midi_out is None or isinstance(musician.midi_out, SynthOutput):
            synth.program_select(
                musician.groover._midi_channel,
                soundfonts[musician.instrument],
                0,
                instruments[musician.instrument],
            )
            if musician.midi_out is None:
                musician.midi_out = SynthOutput(
                    f"LOERIC out #{musician.id}#", synth, index
                )
            else:
                musician.midi_out.channel = index
        musician.ready()
    start_synth()
    play_all()
    return state()


@app.get("/api/pause")
def pause():
    pause_all()
    return state()


@app.get("/api/stop")
def stop():
    global synth_is_running

    stop_all()
    stop_synth()
    for musician in musicians:
        musician.stop()
    return state()


@app.put("/api/instrument")
def instrument_change():
    global musicians
    stop()
    musician_id = request.forms.id
    new_instrument = request.forms.instrument

    for musician in musicians:
        if musician.id == musician_id:
            musician.instrument = new_instrument
            for channel in musician.midi_channels:

                synth.program_select(
                    channel,
                    soundfonts[musician.instrument],
                    0,
                    instruments[musician.instrument],
                )

    return state()


@app.put("/api/control")
def control_change():
    global musicians
    musician_id = request.forms.id
    control = int(request.forms.control)
    new_value = float(request.forms.value)

    for musician in musicians:
        if musician.id == musician_id:
            musician.groover.set_control_value(control, new_value)

    return state()


@app.put("/api/output")
def output_change():
    global musicians
    musician_id = request.forms.id
    new_output = request.forms.output

    for index, musician in enumerate(musicians):
        if musician.id == musician_id:
            stop_synth()
            if new_output == "create_out":
                musician.midi_out = mido.open_output(
                    f"LOERIC out #{musician.id}#", virtual=True
                )
            elif new_output == "synth":
                musician.midi_out = SynthOutput(f"LOERIC Synth {musician.id}", synth)
                start_synth()
            else:
                musician.midi_out = mido.open_output(new_output)

    return state()


@app.put("/api/input")
def input_change():
    global musicians
    musician_id = request.forms.id
    new_input = request.forms.input

    for musician in musicians:
        if musician.id == musician_id:
            musician.stop_threads()
            if new_input == "no_in":
                musician.midi_in = None
                musician.set_input_audio_device(None)
            elif new_input.startswith("audioIn"):
                musician.midi_in = None
                device_index = int(new_input.split(":")[-1])
                musician.set_input_audio_device(device_index)
            else:
                musician.midi_in = mido.open_input(new_input)
                musician.set_input_audio_device(None)

    return state()


@app.get("/api/add_musician")
def add_musician():
    global musicians
    """
    loeric_id = generate(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10
    )
    """
    loeric_id = "WebApp"
    existing = map(lambda m: m.name, musicians)
    unused = list(set(names) - set(existing))
    musician = Musician(unused[0], loeric_id, tune, next(iter(instruments)))
    musicians.append(musician)

    return state()


@app.put("/api/tempo")
def set_tempo():
    global tempo, musicians
    tempo = int(request.forms.tempo)
    for musician in musicians:
        musician.set_tempo(tempo)

    return state()


@app.put("/api/drones")
def set_tempo():
    global musicians
    value = request.forms.drones == "True"
    musician_id = request.forms.id
    print(value)
    for musician in musicians:
        if musician.id == musician_id:
            musician.droning = value

    return state()


@app.put("/api/repeat")
def set_tempo():
    global repetitions
    stop()
    repetitions = int(request.forms.repeats)
    __set_track(current_track)

    return state()


@app.put("/api/audio_out")
def set_audio_out():
    global audio_device_index, synth_is_running

    stop_synth()
    audio_device_index = int(request.forms.device.split(":")[-1])
    start_synth()

    return state()


@app.put("/api/track")
def set_track():
    stop()
    global musicians
    track = request.forms.track
    __set_track(track)
    return state()


@app.get("/api/track")
def get_track():
    return state()


@app.error(405)
def method_not_allowed(res):
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

    return state()


@app.post("/api/track/config")
def upload_track_config():
    global tune
    upload = request.files.get("upload")
    filename = f"tunes/{os.path.splitext(tune.name.lower())[0]}"
    path = webapp_config_path(filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    upload.save(path, overwrite=True)

    tune.config = webapp_load_config(filename)

    return state()
"""


@app.post("/api/track")
def upload_track():
    upload = request.files.get("upload")
    file = os.path.join(track_dir, upload.filename)
    upload.save(file)

    __set_track(track.name + ".mid")

    return state()


@app.get("/")
def get_static():
    return static_file("/index.html", root="static/site")


@app.get("/<filepath:path>")
def get_static(filepath):
    return static_file(filepath, root="static/site")


def init_musician():
    global musicians, synth

    loeric_id = generate(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10
    )
    existing = map(lambda m: m.name, musicians)
    unused = list(set(names) - set(existing))
    musician = Musician(
        name=unused[0],
        loeric_id=loeric_id,
        tune=tune,
        instrument=next(iter(instruments)),
        midi_out=SynthOutput(f"LOERIC Synth {loeric_id}", synth),
    )

    for channel in musician.midi_channels:
        synth.program_select(
            channel,
            soundfonts[musician.instrument],
            0,
            instruments[musician.instrument],
        )

    musicians.append(musician)
    start_synth()


def start_server():
    global audio_device_index, synth_is_running

    load_synths()
    audio_device_index = pa.PyAudio().get_default_output_device_info()["index"]
    track_list = list_tracks()
    if len(track_list) > 0:
        track = track_list[0]
        __set_track(track)
        init_musician()

    run(app, host="localhost", port=8080)
    stop_synth()
