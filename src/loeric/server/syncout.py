from typing import Callable

from mido.ports import BaseOutput

from loeric.groover import Groover
from loeric.server.musician import State


class SyncOutput(BaseOutput):
    def __init__(self, name: str, groover: Groover, set_state: Callable[[State], None], **kwargs):
        self.groover = groover
        self.set_state = set_state
        BaseOutput.__init__(self, name=name, **kwargs)

    def _send(self, msg):
        if msg.type == "sysex" and msg.data[0] == 69:
            tempo = sum(msg.data[1:])
            self.groover.set_tempo(tempo)
            print(f"Received SET TEMPO {tempo}.")
        elif msg.type == "reset":
            self.groover.reset_clock()
            print(f"Received RESET.")
        elif msg.type == "clock":
            self.groover.set_clock()
            print(f"Received CLOCK.")
        elif msg.type == "songpos":
            print(f"Received JUMP {msg.pos}.")
            #if stopped.is_set():
            self.groover.jump_to_pos(msg.pos)
            #else:
            #    print(f"Ignoring JUMP because playback is active.")
        elif msg.type == "start":
            self.set_state(State.PLAYING)
            print("Received START.")
        elif msg.type == "stop":
            self.set_state(State.STOPPED)
            print("Received STOP.")
        elif msg.type == "continue":
            self.set_state(State.PLAYING)
            print("Received CONTINUE.")
        elif msg.type == "control_change":
            for contour_name, event_number in self.groover._config["control_2_contour"].items():
                if msg.is_cc(int(event_number)):
                    value = msg.value / 127
                    self.groover.set_contour_value(contour_name, value)
                    # print(f'"\x1B[0K"{contour_name}:\t{round(value, 2)}', end="\r")
                    print(f"{contour_name}:\t{round(value, 2)}")

    pass
