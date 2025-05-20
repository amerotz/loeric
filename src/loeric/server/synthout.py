import tinysoundfont
from mido.ports import BaseOutput


class SynthOutput(BaseOutput):
    def __init__(self, synth: tinysoundfont.Synth, **kwargs):
        self.synth = synth
        BaseOutput.__init__(self, **kwargs)

    def _send(self, msg):
        if msg.type == "note_on":
            self.synth.noteon(msg.channel, msg.note, msg.velocity)
        elif msg.type == "note_off":
            self.synth.noteoff(msg.channel, msg.note)
        #elif msg.type == "pitchwheel":
            #self.synth.pitchbend(msg.channel, msg.pitch)


    def _close(self):
        self.synth.stop()

    pass
