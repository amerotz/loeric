from os import listdir, getcwd, rename, remove
from os.path import isfile, join, splitext, split
from random import shuffle

import mido
import tinysoundfont
from bottle import Bottle, run, static_file, request, response, HTTPResponse, abort
from mido import MidiFile
from nanoid import generate
from pyaudio import PyAudio

from loeric.server.musician import Musician, get_state, play_all, stop_all, pause_all, Control
from loeric.server.synthout import SynthOutput
from loeric.tune import Tune

track_dir = join(getcwd(), "static/midi")
temp_dir = join(getcwd(), "static/temp")

app = Bottle()

tune: Tune
musicians: list[Musician] = []
names = ["Aoife", "Caoimhe", "Saoirse", "Ciara", "Niamh", "Róisín", "Cara", "Clodagh", "Aisling", "Éabha",
         "Conor", "Sean", "Oisín", "Patrick", "Cian", "Liam", "Darragh", "Eoin", "Caoimhín", "Cillian"]
shuffle(names)

instruments = {"Accordion": 21, "Guitar": 24, "Harp": 46, "Flute": 73, "Violin": 40}

synth = tinysoundfont.Synth()
soundfont_id = 0


def list_audio():
    audio = PyAudio()
    info = audio.get_host_api_info_by_index(0)
    device_count = info.get("deviceCount")

    list = {}

    for i in range(0, device_count):
        if (audio.get_device_info_by_host_api_device_index(0, i).get("maxInputChannels")) > 0:
            name = audio.get_device_info_by_host_api_device_index(0, i).get("name")
            list[name] = i

    return list


@app.get('/api/state')
def state():
    response.set_header('Access-Control-Allow-Origin', '*')
    return {
        'musicians': list(map(lambda m: m.__json__(), musicians)),
        'state': get_state().name,
        'track': {
            'name': split(tune.filename)[1],
            'time': f"{tune.time_signature.numerator}/{tune.time_signature.denominator}",
            'key': tune.key_signature,
            'tempo': mido.tempo2bpm(tune.tempo, [tune.time_signature.numerator, tune.time_signature.denominator]),
        },
        'options': {
            'inputs': mido.get_input_names(),
            'outputs': mido.get_output_names(),
            'instruments': list(instruments.keys()),
            'trackList': [f for f in listdir(track_dir) if
                          isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid'],
            'audio': list_audio()
        },
    }


def __set_track(track: str):
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    if track in track_list:
        global tune
        tune = Tune(join(track_dir, track), 1, "reel")
        for musician in musicians:
            musician.tune = tune


@app.get('/api/play')
def play():
    for index, musician in enumerate(musicians):
        if musician.midi_out is None or isinstance(musician.midi_out, SynthOutput):
            synth.program_select(index, soundfont_id, 0, instruments[musician.instrument])
            if musician.midi_out is None:
                musician.midi_out = SynthOutput(f"Loeric Synth #{musician.id}", synth, index)
            else:
                musician.midi_out.channel = index
        musician.ready()
    synth.start()
    play_all()
    return state()


@app.get('/api/pause')
def pause():
    pause_all()
    return state()


@app.get('/api/stop')
def stop():
    stop_all()
    synth.stop()
    return state()


@app.put('/api/instrument')
def instrument_change():
    global musicians
    musician_id = request.forms.id
    new_instrument = request.forms.instrument

    for musician in musicians:
        if musician.id == musician_id:
            musician.instrument = new_instrument

    return state()


@app.put('/api/control')
def control_change():
    global musicians
    musician_id = request.forms.id
    control = int(request.forms.control_out)
    new_value = int(request.forms.value)

    for musician in musicians:
        if musician.id == musician_id:
            if musician.midi_out is not None:
                musician.set_control(control, new_value)

    return state()


@app.put('/api/output')
def output_change():
    global musicians
    musician_id = request.forms.id
    new_output = request.forms.output

    for index, musician in enumerate(musicians):
        if musician.id == musician_id:
            if new_output == 'create_output':
                musician.midi_in = mido.open_output(f"Loeric Virtual Out {musician.id}", virtual=True)
            elif new_output == 'synth':
                musician.midi_in = SynthOutput(f"Loeric Synth {musician.id}", synth, index)
            else:
                musician.midi_in = mido.open_output(new_output)

    return state()


@app.put('/api/input')
def input_change():
    global musicians
    musician_id = request.forms.id
    new_input = request.forms.input

    for musician in musicians:
        if musician.id == musician_id:
            if new_input == 'no_in':
                musician.midi_in = None
            else:
                musician.midi_in = new_input

    return state()


@app.get('/api/add_musician')
def add_musician():
    global musicians
    loeric_id = generate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", 10)
    existing = map(lambda m: m.name, musicians)
    unused = list(set(names) - set(existing))
    musicians.append(Musician(unused[0], loeric_id, tune, next(iter(instruments)), [Control("Volume", 7, 127), Control("Intensity", 21, 127)]))

    return state()


@app.put('/api/track')
def set_track():
    global musicians
    track = request.forms.track
    __set_track(track)
    return state()


@app.get('/api/track')
def get_track():
    return state()


@app.error(405)
def method_not_allowed(res):
    if request.method == 'OPTIONS':
        new_res = HTTPResponse()
        new_res.set_header('Access-Control-Allow-Methods', 'POST, PUT, GET, OPTIONS')
        new_res.set_header('Access-Control-Allow-Origin', '*')
        return new_res
    res.headers['Allow'] += ', OPTIONS'
    return request.app.default_error_handler(res)


@app.post('/api/track')
def upload_track():
    upload = request.files.get('upload')
    temp_file = join(temp_dir, upload.filename)
    upload.save(temp_file)

    try:
        mido_source = MidiFile(temp_file)
        for i, track in enumerate(mido_source.tracks):
            print('Track {}: {}'.format(i, track.name))
            for msg in track:
                print(msg)
        track = mido_source.tracks[0]
        track_file = join(track_dir, track.name + '.mid')
        rename(temp_file, track_file)

        __set_track(track.name + '.mid')
    except:
        remove(temp_file)
        return abort(401, 'Not a recognised midi file')

    return state()


@app.get("/")
def get_static():
    return static_file('/index.html', root="static/site")


@app.get("/<filepath:path>")
def get_static(filepath):
    return static_file(filepath, root="static/site")


def start_server():
    global soundfont_id
    soundfont_id = synth.sfload("static/sound/FluidR3_GM.sf2")
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    if len(track_list) > 0:
        track = track_list[0]
        if track in track_list:
            global tune
            tune = Tune(join(track_dir, track), 1)
            add_musician()

    run(app, host='localhost', port=8080)
    synth.stop()
