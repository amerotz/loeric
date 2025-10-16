import tinysoundfont
from mido.ports import BaseOutput


class SynthOutput(BaseOutput):
    def __init__(self, name: str, synth: tinysoundfont.Synth, **kwargs):
        self.synth = synth
        BaseOutput.__init__(self, name=name, **kwargs)

    def _send(self, msg):
        if msg.type == "note_on":
            self.synth.noteon(msg.channel, msg.note, msg.velocity)
        elif msg.type == "note_off":
            self.synth.noteoff(msg.channel, msg.note)
        elif msg.type == "pitchwheel":
            self.synth.pitchbend(msg.channel, msg.pitch + 8192)
        elif msg.type == "control_change":
            self.synth.control_change(msg.channel, msg.control, msg.value)
        else:
            print("Unknown message type: ", msg.type)

    pass
