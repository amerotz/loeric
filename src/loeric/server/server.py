import time
from os import listdir, getcwd, rename, remove
from os.path import isfile, join, splitext, split

import mido
from bottle import Bottle, run, static_file, request, response, HTTPResponse, abort
from mido import MidiFile

from loeric.server.musician import Musician, get_state, play_all, stop_all
from loeric.tune import Tune

track_dir = join(getcwd(), "static/midi")
temp_dir = join(getcwd(), "static/temp")

app = Bottle()

tune: Tune
musicians: list[Musician] = []


@app.get('/api/state')
def state():
    response.set_header('Access-Control-Allow-Origin', '*')
    return {
        'time': f"{tune.time_signature.numerator}/{tune.time_signature.denominator}",
        'key': tune.key_signature,
        'tempo': mido.tempo2bpm(tune.tempo, [tune.time_signature.numerator, tune.time_signature.denominator]),
        'track': split(tune.filename)[1],
        'trackList': [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid'],
        'outputs': mido.get_output_names(),
        'musicians': list(map(lambda m: m.__json__(), musicians)),
        'state': get_state().name
    }


def __set_track(track: str):
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    if track in track_list:
        global tune
        tune = Tune(join(track_dir, track), 1)
        for musician in musicians:
            musician.tune = tune


@app.get('/api/play')
def play():
    for musician in musicians:
        musician.ready()
    play_all()
    return state()


@app.get('/api/stop')
def stop():
    stop_all()
    return state()


@app.get('/api/add_musician')
def add_musician():
    global musicians
    loeric_id = int(time.time())
    name = "Musician " + str(len(musicians) + 1)
    musicians.append(Musician(name, loeric_id, tune, None))

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
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    if len(track_list) > 0:
        track = track_list[0]
        if track in track_list:
            global tune
            tune = Tune(join(track_dir, track), 1)
            add_musician()

    run(app, host='localhost', port=8080)
