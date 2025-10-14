from os import listdir, getcwd, rename, remove, makedirs
from os.path import isfile, join, splitext, dirname, realpath
from random import shuffle
from typing import List

import mido
import tinysoundfont
from bottle import Bottle, run, static_file, request, response, HTTPResponse, abort
from mido import MidiFile, Message
from muspy import KeySignature
from muspy.outputs.midi import PITCH_NAMES
from nanoid import generate
import pyaudio as pa

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
from loeric.loeric_config.loeric_config import webapp_load_config, webapp_config_path

track_dir = join(getcwd(), "static/midi")
temp_dir = join(getcwd(), "static/temp")

app = Bottle()

tune: Tune
musicians: list[Musician] = []
names = ["Larry"]
shuffle(names)

instruments = {"Accordion": 21, "Guitar": 24, "Harp": 46, "Flute": 73, "Violin": 40}

synth = tinysoundfont.Synth()
synth_is_running = False
soundfont_id = 0
audio_device_index = 0
tempo = 140

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


def key_to_str(key: KeySignature) -> str:
    if key.root is None:
        return ""
    if key.mode not in ("major", "minor"):
        return ""
    suffix = " Minor" if key.mode == "minor" else ""
    return f"{PITCH_NAMES[key.root]}{suffix}"


def trim_ext(file: str) -> str:
    return splitext(file)[0]


def list_tracks() -> List[str]:
    return [
        f
        for f in listdir(track_dir)
        if isfile(join(track_dir, f)) and splitext(f)[1].casefold() in filetypes
    ]


@app.get("/api/state")
def state():
    global tune, tempo
    response.set_header("Access-Control-Allow-Origin", "*")
    return {
        "musicians": list(map(lambda m: m.__json__(), musicians)),
        "state": get_state().name,
        "track": {
            "name": tune.name,
            "time": f"{tune.time_signature.numerator}/{tune.time_signature.denominator}",
            # "config": tune.config,
            "key": key_to_str(tune.key_signature),
            "tempo": tempo,
        },
        "options": {
            "inputs": mido.get_input_names(),
            "outputs": mido.get_output_names(),
            "instruments": list(instruments.keys()),
            "trackList": list_tracks(),
            "audio_inputs": list_audio_inputs(),
            "audio_outputs": list_audio_outputs(),
        },
    }


def __set_track(track: str):
    global tune
    track_list = list_tracks()
    if track in track_list:
        tune = Tune(join(track_dir, track), 1)

        tune.config = webapp_load_config(f"tunes/{splitext(tune.name.lower())[0]}")

        for musician in musicians:
            musician.tune = tune


@app.get("/api/play")
def play():
    global synth_is_running, musicians
    for index, musician in enumerate(musicians):
        if musician.midi_out is None or isinstance(musician.midi_out, SynthOutput):
            synth.program_select(
                musician.groover._midi_channel,
                soundfont_id,
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
    synth.sounds_off()
    stop_synth()
    for musician in musicians:
        musician.stop()
    return state()


@app.put("/api/instrument")
def instrument_change():
    global musicians, soundfont_id
    stop()
    musician_id = request.forms.id
    new_instrument = request.forms.instrument

    for musician in musicians:
        if musician.id == musician_id:
            musician.instrument = new_instrument
            for channel in musician.midi_channels:
                synth.program_select(
                    channel, soundfont_id, 0, instruments[musician.instrument]
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
                musician.midi_out = SynthOutput(
                    f"LOERIC Synth {musician.id}", synth, index
                )
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
            if new_input == "no_in":
                musician.midi_in = None
            else:
                musician.midi_in = new_input

    return state()


@app.get("/api/add_musician")
def add_musician():
    global musicians
    loeric_id = generate(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10
    )
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


@app.put("/api/audio_out")
def set_audio_out():
    global audio_device_index, synth_is_running

    stop()
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


@app.post("/api/musician/config")
def upload_musician_config():
    global musicians
    musician_id = request.forms.id
    for index, musician in enumerate(musicians):
        if musician.id == musician_id:
            upload = request.files.get("upload")
            filename = f"musician/{musician.name}"
            path = webapp_config_path(filename)
            makedirs(dirname(path), exist_ok=True)
            upload.save(path, overwrite=True)

            musician.config = webapp_load_config(filename)

    return state()


@app.post("/api/track/config")
def upload_track_config():
    global tune
    upload = request.files.get("upload")
    filename = f"tunes/{splitext(tune.name.lower())[0]}"
    path = webapp_config_path(filename)
    makedirs(dirname(path), exist_ok=True)
    upload.save(path, overwrite=True)

    tune.config = webapp_load_config(filename)

    return state()


@app.post("/api/track")
def upload_track():
    upload = request.files.get("upload")
    file = join(track_dir, upload.filename)
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
    global musicians, synth, soundfont_id

    loeric_id = generate(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10
    )
    existing = map(lambda m: m.name, musicians)
    unused = list(set(names) - set(existing))
    musician = Musician(unused[0], loeric_id, tune, next(iter(instruments)))

    for channel in musician.midi_channels:
        synth.program_select(channel, soundfont_id, 0, instruments[musician.instrument])

    musician.midi_out = SynthOutput(f"LOERIC Synth {musician.id}", synth, 0)

    musicians.append(musician)
    start_synth()


def start_server():
    global audio_device_index, soundfont_id, synth_is_running
    soundfont_id = synth.sfload("static/sound/FluidR3_GM.sf2")

    audio_device_index = pa.PyAudio().get_default_output_device_info()["index"]
    track_list = list_tracks()
    if len(track_list) > 0:
        track = track_list[0]
        __set_track(track)
        init_musician()

    run(app, host="localhost", port=8080)
    stop_synth()
