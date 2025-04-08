from os import listdir, getcwd
from os.path import isfile, join, splitext

from bottle import Bottle, run, static_file, request
from loeric import tune, groover

track_dir = join(getcwd(), "static/midi")

app = Bottle()

tune = tune.Tune("", 0)
groover = groover.Groover(
    tune,
    bpm=args["bpm"],
    midi_channel=args["midi_channel"],
    transpose=args["transpose"],
    diatonic_errors=args["diatonic"],
    random_weight=0.2,
    human_impact=args["human_impact"],
    seed=args["seed"],
    config_file=args["config"],
    syncing=args["sync"],
)

@app.get('/api/hello')
def hello():
    return "Hello World!"


@app.get('/api/state')
def hello():
    track_list = [f for f in listdir(track_dir) if isfile(join(track_dir, f)) and splitext(f)[1].casefold() == '.mid']
    return {
        'track': '',
        'trackList': track_list
    }

@app.put('/api/track')
def set_track(track):
    return {}


@app.post('/api/track')
def upload_track():
    upload     = request.files.get('upload')
    name, ext = splitext(upload.filename)
    if ext.casefold() == '.mid':
        return 'File extension not allowed.'

    # TODO Check for existing files...

    upload.save(track_dir) # appends upload.filename automatically
    return 'OK'


@app.get("/")
def get_static():
    return static_file('/index.html', root="static/site")

@app.get("/<filepath:path>")
def get_static(filepath):
    return static_file(filepath, root="static/site")

def start_server():
    run(app, host='localhost', port=8080)