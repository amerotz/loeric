import threading
import time
from os import listdir, getcwd
from os.path import isfile, join, splitext, split

import mido
from bottle import Bottle, run, static_file, request, response, HTTPResponse, abort

from loeric.groover import Groover
from loeric.server.musician import Musician
from loeric.tune import Tune

track_dir = join(getcwd(), "static/midi")

event_start = threading.Semaphore(value=0)
event_stop = threading.Event()

app = Bottle()

musicians = []


@app.get('/api/state')
def state():
    response.set_header('Access-Control-Allow-Origin', '*')
    return {
        'time': f"{tune.time_signature.numerator}/{tune.time_signature.denominator}",
        'key': tune.key_signature,
        'track': split(tune.filename)[1],
        'trackList': [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid'],
        'outputs': mido.get_output_names(),
        'musicians': list(map(lambda m: m.__json__(), musicians)),
    }


@app.get('/api/play')
def play():
    for musician in musicians:
        musician.stop()
        musician.play()
    event_start.release(n=2)
    return state()


@app.get('/api/stop')
def stop():
    for musician in musicians:
        musician.stop()
    return state()


@app.put('/api/track')
def set_track():
    global musicians
    track = request.forms.track
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    if track in track_list:
        global tune
        tune = Tune(join(track_dir, track), 2)
        groover = Groover(tune)
        for musician in musicians:
            musician.groover = groover
    return state()


@app.get('/api/track')
def get_track():
    global musicians
    track = request.forms.track
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    if track in track_list:
        global tune
        tune = Tune(join(track_dir, track), 1)
        groover = Groover(tune)
        for musician in musicians:
            musician.groover = groover
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
    name, ext = splitext(upload.filename)
    if ext.casefold() != '.mid':
        return abort(401, 'File extension not allowed.')

    # TODO Check for existing files...

    upload.save(track_dir)  # appends upload.filename automatically
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
            print(join(track_dir, track))
            global tune
            tune = Tune(join(track_dir, track), 2)
            groover = Groover(tune)
            global musicians
            loeric_id = int(time.time())
            musicians = [Musician(loeric_id, tune, groover, None, event_start, event_stop)]

    run(app, host='localhost', port=8080)
