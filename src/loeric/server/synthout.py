import tinysoundfont
from mido.ports import BaseOutput


class SynthOutput(BaseOutput):
    def __init__(self, synth: tinysoundfont.Synth, channel: int, **kwargs):
        self.synth = synth
        self.channel = channel
        BaseOutput.__init__(self, **kwargs)

    def _send(self, msg):
        if msg.type == "note_on":
            self.synth.noteon(self.channel, msg.note, msg.velocity)
        elif msg.type == "note_off":
            self.synth.noteoff(self.channel, msg.note)
        elif msg.type == "pitchwheel":
            self.synth.pitchbend(self.channel, msg.pitch + 8192)
        elif msg.type == "control_change":
            self.synth.control_change(self.channel, msg.control, msg.value)
        else:
            print("Unknown message type: ", msg.type)

    pass
