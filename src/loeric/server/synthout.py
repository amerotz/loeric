import tinysoundfont
from mido.ports import BaseOutput


class SynthOutput(BaseOutput):
    def __init__(self, synth: tinysoundfont.Synth, channel: int, **kwargs):
        self.synth = synth
        self.channel = channel
        BaseOutput.__init__(self, **kwargs)

    def _send(self, msg):
        print(msg)
        if msg.type == "note_on":
            self.synth.noteon(msg.channel, msg.note, msg.velocity)
        elif msg.type == "note_off":
            self.synth.noteoff(msg.channel, msg.note)

    pass
