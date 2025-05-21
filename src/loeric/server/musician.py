import faulthandler
import threading
from enum import Enum
from random import randint
from typing import Optional

import mido
from mido.ports import BaseOutput, BaseInput

from loeric import (loeric_utils as lu)
from loeric.groover import Groover
from loeric.player import Player
from loeric.tune import Tune

faulthandler.enable()
# bad code goes here

class State(Enum):
    STOPPED = 0
    PAUSED = 1
    PLAYING = 2

_state = State.STOPPED
_lock = threading.Lock()
_play_event = threading.Event()

def get_state() -> State:
    return _state


def play_all():
    _update(State.PLAYING)


def pause_all():
    _update(State.PAUSED)


def stop_all():
    _update(State.STOPPED)


def _update(state: State):
    global _state
    _lock.acquire()
    _state = state
    _lock.release()
    if state == State.PLAYING:
        _play_event.set()
    else:
        _play_event.clear()


class Musician:
    def __init__(
            self,
            name: str,
            loeric_id: str,
            tune: Tune,
            instrument: int,
            midi_out: str | BaseOutput | None = None,
            midi_in: str | None = None,
    ):
        self.name = name
        self.id = loeric_id
        self.tune = tune
        self.instrument = instrument
        self.midi_out = midi_out
        self.midi_in = midi_in
        self.seed = randint(0,1000000)
        self.random_weight = 0.2
        self.thread = threading.Thread()


    def ready(self)-> None:
        global _state
        if _state == State.STOPPED:
            self.thread = threading.Thread(target=self.__play)
            self.thread.start()


    def __play(self, )-> None:
        try:
            """
            Play the given tune with the given groover.
    
            :param loeric_id: the id of the current LOERIC istance
            :param groover: the groover object
            :param tune: the tune object
            :param sync_port_out: the MIDI port for synchronization
            :param kwargs: the performance arguments
            """
            global _play_event, _state
            midi_output: Optional[BaseOutput] = None
            if self.midi_out is None:
                midi_output = mido.open_output(f"LOERIC out #{self.id}#", virtual=True)
            elif isinstance(self.midi_out, BaseOutput):
                midi_output = self.midi_out
                midi_output.reset()
            else:
                midi_output = mido.open_output(self.midi_out)

            groover = Groover(
                self.tune,
                random_weight=self.random_weight,
                seed=self.seed
            )

            midi_input: Optional[BaseInput] = None
            if self.midi_in is not None:
                midi_input = mido.open_input(self.midi_in)
                midi_input.callback = groover.check_midi_control()

            # create player
            player = Player(
                tempo=groover.tempo,
                key_signature=self.tune.key_signature,
                time_signature=self.tune.time_signature,
                save=False,
                midi_out=midi_output,
            )

            # wait for start
            _play_event.wait()
            player.init_playback()

            # repeat as specified
            # iterate over messages
            while True:
                if _state == State.PAUSED:
                    player.reset()
                    _play_event.wait()
                    player.init_playback()
                elif _state == State.STOPPED:
                    break
                message = groover.next_event()
                if message is None:
                    break

                if message.type == "sysex":
                    #print(f"Repetition {message.data[0] + 1}/{kwargs['repeat']}")
                    continue
                # perform notes
                elif lu.is_note(message):
                    # make the groover play the messages
                    new_messages = groover.perform(message)
                # keep meta messages intact
                else:
                    if message.type == "songpos":
                        #if sync_port_out is not None:
                            #sync_port_out.send(message)
                            # print(f"{loeric_id} SENT {message.pos} ({time.time()})")
                        new_messages = []
                    else:
                        new_messages = [message]
                # play
                player.play(new_messages)

            _update(State.STOPPED)

            if midi_input is not None:
                midi_input.close()
                if midi_input.closed:
                    print("Closed MIDI input.")

            # make sure to turn off all notes
            if midi_output is not None:
                for i in range(127):
                    midi_output.send(mido.Message("note_off", velocity=0, note=i, time=0))
                midi_output.reset()
                midi_output.close()
                if midi_output.closed:
                    print("Closed MIDI output.")

            print("Player thread terminated.")

        except Exception as e:
            # stop sync thread
            _update(State.STOPPED)
            print("Player thread terminated.")
            raise e

    def __json__(self):
        out = self.midi_out
        if isinstance(self.midi_out, BaseOutput):
            out = self.midi_out.name
        return {'id': self.id, 'name': self.name, 'midiOut': out, 'midiIn': self.midi_in, 'instrument': self.instrument}