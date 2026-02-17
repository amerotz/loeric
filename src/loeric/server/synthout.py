import os

import tinysoundfont
from mido.ports import BaseOutput


class SynthSound:

    def __init__(
        self,
        name,
        path,
        program,
        config,
        default_soundfont_id=0,
        default_program=0,
        default_config=None,
        gain=0,
    ):

        self._name = name
        self._path = path
        self._program = program
        self._soundfont_id = None
        self._is_default = True
        self._config = config

        self._default_soundfont_id = default_soundfont_id
        self._default_program = default_program
        self._default_config = default_config

        self._gain = gain

    def load(self, synth):
        if not os.path.isfile(self._path):
            self._is_default = True
        else:
            self._is_default = False
            self._soundfont_id = synth.sfload(self._path, gain=self._gain)

    def unload(self, synth):
        if self._soundfont_id is not None:
            synth.sfunload(self._soundfont_id)

    @property
    def name(self):
        return self._name

    @property
    def soundfont_id(self):
        if self._is_default:
            return self._default_soundfont_id
        else:
            return self._soundfont_id

    @property
    def program(self):
        if self._is_default:
            return self._default_program
        else:
            return self._program

    @property
    def config(self):
        if self._is_default:
            return self._default_config
        else:
            return self._config


class SynthOutput(BaseOutput):
    def __init__(self, name: str, synth: tinysoundfont.Synth, **kwargs):
        self._synth = synth
        BaseOutput.__init__(self, name=name, **kwargs)

    def _send(self, msg):
        if msg.type == "note_on":
            self._synth.noteon(msg.channel, msg.note, msg.velocity)
        elif msg.type == "note_off":
            self._synth.noteoff(msg.channel, msg.note)
        elif msg.type == "pitchwheel":
            self._synth.pitchbend(msg.channel, msg.pitch + 8192)
        elif msg.type == "control_change":
            self._synth.control_change(msg.channel, msg.control, msg.value)
        else:
            print("[WARN]\tUnknown MIDI message type: ", msg.type)
