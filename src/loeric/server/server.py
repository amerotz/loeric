import os
import json
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
import loeric.server.synthout as lss
from loeric.tune import Tune

track_dir = os.path.join(os.getcwd(), "static/midi")
temp_dir = os.path.join(os.getcwd(), "static/temp")
general_configs_path = os.getcwd() + "/src/loeric/loeric_config/performance"
specific_configs_path = os.path.join(os.getcwd(), "static/webapp_configs")

app = Bottle()

musicians: list[Musician] = []
names = ["LOERIC"]
shuffle(names)

synth = None  # , tinysoundfont.Synth()
synth_is_running = False
soundfonts = []


def load_soundfonts():
    global synth, soundfonts
    default_soundfont_id = synth.sfload("static/sound/FluidR3_GM.sf2")
    soundfonts = {
        "Accordion": lss.SynthSound(
            name="Accordion",
            path="static/sound/Diato.sf2",
            program=1,
            config=f"{specific_configs_path}/instrument/accordion.json",
            default_soundfont_id=default_soundfont_id,
            default_program=21,
            default_config=f"{specific_configs_path}/instrument/default_accordion.json",
        ),
        "Guitar": lss.SynthSound(
            name="Guitar",
            path="static/sound/MusicLab_Acoustic_Guitars.sf2",
            program=25,
            config=f"{specific_configs_path}/instrument/guitar.json",
            default_soundfont_id=default_soundfont_id,
            default_program=25,
            default_config=f"{specific_configs_path}/instrument/guitar.json",
        ),
        "Piano": lss.SynthSound(
            name="Piano",
            path="static/sound/piano.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/piano.json",
            default_soundfont_id=default_soundfont_id,
            default_program=0,
            default_config=f"{specific_configs_path}/instrument/piano.json",
        ),
        "Harp": lss.SynthSound(
            name="Harp",
            path="static/sound/Celtic Harp.sf2",
            program=46,
            config=f"{specific_configs_path}/instrument/harp.json",
            default_soundfont_id=default_soundfont_id,
            default_program=46,
            default_config=f"{specific_configs_path}/instrument/harp.json",
        ),
        "Flute": lss.SynthSound(
            name="Flute",
            path="static/sound/FLUTE2.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/flute.json",
            default_soundfont_id=default_soundfont_id,
            default_program=73,
            default_config=f"{specific_configs_path}/instrument/default_flute.json",
        ),
        "Violin": lss.SynthSound(
            name="Violin",
            path="static/sound/violin.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/violin.json",
            default_soundfont_id=default_soundfont_id,
            default_program=40,
            default_config=f"{specific_configs_path}/instrument/violin.json",
        ),
        "Saw": lss.SynthSound(
            name="Saw",
            path="static/sound/saw.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/piano.json",
            default_soundfont_id=default_soundfont_id,
            default_program=81,
            default_config=f"{specific_configs_path}/instrument/piano.json",
        ),
        "Square": lss.SynthSound(
            name="Square",
            path="static/sound/saw.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/piano.json",
            default_soundfont_id=default_soundfont_id,
            default_program=80,
            default_config=f"{specific_configs_path}/instrument/piano.json",
        ),
        "Polysynth": lss.SynthSound(
            name="Polysynth",
            path="static/sound/saw.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/piano.json",
            default_soundfont_id=default_soundfont_id,
            default_program=90,
            default_config=f"{specific_configs_path}/instrument/piano.json",
        ),
        "Fantasia": lss.SynthSound(
            name="Fantasia",
            path="static/sound/saw.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/piano.json",
            default_soundfont_id=default_soundfont_id,
            default_program=88,
            default_config=f"{specific_configs_path}/instrument/piano.json",
        ),
        "Vox": lss.SynthSound(
            name="Vox",
            path="static/sound/saw.sf2",
            program=0,
            config=f"{specific_configs_path}/instrument/piano.json",
            default_soundfont_id=default_soundfont_id,
            default_program=85,
            default_config=f"{specific_configs_path}/instrument/piano.json",
        ),
    }

    for sound in soundfonts.values():
        sound.load(synth)


audio_device_index = 0
tempo = 140
repetitions = 2
current_track = None
filetypes = [".mid", ".abc", ".set"]


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
    return sorted(
        [
            f
            for f in os.listdir(track_dir)
            if os.path.isfile(os.path.join(track_dir, f))
            and os.path.splitext(f)[1].casefold() in filetypes
        ]
    )


def list_custom_tracks() -> List[str]:
    configs = os.listdir(specific_configs_path + "/tunes")
    return [f for f in list_tracks() if f.split(".")[0] + ".json" in configs]


@app.get("/api/state")
def state():
    global tempo, repetitions
    response.set_header("Access-Control-Allow-Origin", "*")
    return {
        "musicians": list(map(lambda m: m.__json__(), musicians)),
        "state": get_state().name,
        "track": {
            "name": current_track,
            "time": f"{musicians[0].tune.time_signature.numerator}/{musicians[0].tune.time_signature.denominator}",
            "config": musicians[0].tune.get_config(),
            "key": key_to_str(musicians[0].tune.key_signature),
            "tempo": musicians[0].groover.tempo.qpm,
            "repeats": musicians[0].tune.repeats,
        },
        "options": {
            "inputs": mido.get_input_names(),
            "outputs": mido.get_output_names(),
            "instruments": list(soundfonts.keys()),
            "trackList": list_tracks(),
            "customized_tracks": list_custom_tracks(),
            "audio_inputs": list_audio_inputs(),
            "audio_outputs": list_audio_outputs(),
            "selected_audio_out": audio_device_index,
        },
    }


def __set_track(track: str):
    global repetitions, current_track

    current_track = track
    track_list = list_tracks()

    if track in track_list:

        tunes = []
        if os.path.splitext(track)[1] == ".set":

            with open(os.path.join(track_dir, track), "r") as f:
                set_config = json.load(f)

            for t in set_config:
                tune_config = f"{specific_configs_path}/tunes/{os.path.splitext(t["file"])[0]}.json"
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
                    f"{specific_configs_path}/tunes/{os.path.splitext(track)[0]}.json",
                    0,
                    tempo,
                )
            )

        for musician in musicians:
            musician._tunes = []
            musician._tempos = []

        for name, repeats, config, trim, qpm in tunes:
            tune = Tune(
                filename=os.path.join(track_dir, name),
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
def play():
    global synth_is_running, musicians
    for index, musician in enumerate(musicians):
        if musician.midi_out is None or isinstance(musician.midi_out, lss.SynthOutput):
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
            musician.instrument = soundfonts[new_instrument]
            for channel in musician.midi_channels:

                synth.program_select(
                    channel,
                    soundfonts[musician.instrument].soundfont_id,
                    0,
                    soundfonts[musician.instrument].program,
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
            musician.set_control_value(control, new_value)

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
                musician.midi_out = lss.SynthOutput(
                    f"LOERIC Synth {musician.id}", synth
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
        musician.stop_threads()
        if musician.id == musician_id:
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
    instrument_key = next(iter(soundfonts))
    musician = Musician(
        name=unused[0],
        loeric_id=loeric_id,
        synth_sound=soundfonts[instrument_key],
    )
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
def set_drones():
    global musicians
    value = request.forms.drones == "true"
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.groover.set_droning(value)

    return state()


@app.put("/api/slow_start")
def set_slow_start():
    stop()
    global musicians
    value = request.forms.slow_start == "true"
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.slow_start = value

    return state()


@app.put("/api/slow_end")
def set_slow_end():
    global musicians
    stop()
    value = request.forms.slow_end == "true"
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.slow_end = value

    return state()


@app.put("/api/transpose")
def set_transpose():
    global musicians
    value = int(request.forms.transpose)
    print(value)
    musician_id = request.forms.id
    for musician in musicians:
        if musician.id == musician_id:
            musician.set_transpose(value)

    return state()


@app.put("/api/repeat")
def set_repeat():
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

    return state()


@app.get("/")
def get_static():
    return static_file("/index.html", root="static/site")


@app.get("/<filepath:path>")
def get_static(filepath):
    return static_file(filepath, root="static/site")


def init_musician(track):
    global musicians, synth

    loeric_id = generate(
        "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10
    )
    existing = map(lambda m: m.name, musicians)
    unused = list(set(names) - set(existing))
    instrument_key = next(iter(soundfonts))
    musician = Musician(
        name=unused[0],
        loeric_id=loeric_id,
        synth_sound=soundfonts[instrument_key],
        midi_out=lss.SynthOutput(f"LOERIC Synth {loeric_id}", synth),
    )
    musicians.append(musician)

    __set_track(track)

    for channel in musician.midi_channels:
        synth.program_select(
            channel,
            soundfonts[musician.instrument].soundfont_id,
            0,
            soundfonts[musician.instrument].program,
        )

    start_synth()


def start_server():
    global audio_device_index, synth, synth_is_running

    synth = tinysoundfont.Synth()
    load_soundfonts()

    audio_device_index = pa.PyAudio().get_default_output_device_info()["index"]
    track_list = list_tracks()
    if len(track_list) > 0:
        track = track_list[0]
        init_musician(track)

    run(app, host="localhost", port=8080, quiet=True)
    stop_synth()
