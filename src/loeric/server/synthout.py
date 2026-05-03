"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import os

import tinysoundfont
from mido.ports import BaseOutput


file_to_soundfont_id = {}


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
        global file_to_soundfont_id
        if not os.path.isfile(self._path):
            self._is_default = True
        else:
            self._is_default = False
            if self._path in file_to_soundfont_id:
                # get sf id
                self._soundfont_id = file_to_soundfont_id[self._path][0]
                # add another instrument to sf
                file_to_soundfont_id[self._path][1] += 1
            else:
                # load sf
                self._soundfont_id = synth.sfload(self._path, gain=self._gain)
                # add to dict
                file_to_soundfont_id[self._path] = [self._soundfont_id, 1]

    def unload(self, synth):
        if self._soundfont_id is not None:
            synth.sfunload(self._soundfont_id)
            # reduce count of active instruments
            file_to_soundfont_id[self._path][1] -= 1
            # if 0 remove from dict
            if file_to_soundfont_id[self._path][1] == 0:
                del file_to_soundfont_id[self._path]

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
            print(
                f"\033[38;2;255;255;0m[WARN]\tUnknown MIDI message type: ",
                msg.type,
                "\033[0m",
            )
