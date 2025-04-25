import faulthandler
import threading
from typing import Optional

import mido
from mido.ports import BaseOutput

from loeric import groover as gr
from loeric import (loeric_utils as lu)
from loeric import player as pl
from loeric import tune as tu

faulthandler.enable()
# bad code goes here

class Musician:
    def __init__(
            self,
            loeric_id: int,
            tune: tu.Tune,
            groover: gr.Groover,
            out: Optional[str],
            event_start: threading.Semaphore,
            event_stop: threading.Event,
    ):
        self.loeric_id = loeric_id
        self.tune = tune
        self.groover = groover
        self.out = out
        self.done_playing = threading.Event()
        self.playback_resumed = threading.Condition()
        self.groover_lock = threading.Lock()
        self.event_start = event_start
        self.event_stop = event_stop


    def stop(self):
        self.event_stop.set()


    def play(self)-> None:
        self.event_stop.clear()
        self.player_t = threading.Thread(target=self.__play)
        self.player_t.start()


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
            out: Optional[BaseOutput] = None
            if(self.out == None):
                out = mido.open_output(f"LOERIC out #{self.loeric_id}#", virtual=True)
            else:
                out = mido.open_output(self.out)

            # create player
            self.player = pl.Player(
                tempo=self.groover.tempo,
                key_signature=self.tune.key_signature,
                time_signature=self.tune.time_signature,
                save=False,
                verbose=False,
                midi_out=self.out,
            )

            # wait for start
            self.event_start.acquire()
            self.player.init_playback()

            # repeat as specified
            # iterate over messages
            while True:
                if self.event_stop.is_set():
                    self.player.reset()
                    with self.playback_resumed:
                        self.playback_resumed.wait()
                    self.player.init_playback()
                message = self.groover.next_event()
                if message is None:
                    break

                if message.type == "sysex":
                    #print(f"Repetition {message.data[0] + 1}/{kwargs['repeat']}")
                    continue
                # perform notes
                elif lu.is_note(message):
                    # make the groover play the messages
                    new_messages = self.groover.perform(message)
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
                self.player.play(new_messages)

            # play an end note
            #if not kwargs["no_end_note"]:
            self.groover.reset_contours()
            self.groover.jump_to_pos(0)
            self.player.play(self.groover.get_end_notes())

            self.done_playing.set()
            print("Player thread terminated.")

        except Exception as e:
            # stop sync thread
            self.done_playing.set()
            print("Player thread terminated.")
            raise e

    def __json__(self):
        return {'id': self.loeric_id, 'out': self.out}