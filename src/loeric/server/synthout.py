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
        #elif msg.type == "pitchwheel":
            #self.synth.pitchbend(msg.channel, msg.pitch)


    def _close(self):
        self.synth.stop()

    pass
