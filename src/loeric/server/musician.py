import faulthandler
import os
import threading
from collections.abc import Callable

import mido

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
            groover: gr.Groover,
    ):
        self.loeric_id = loeric_id
        self.groover = groover
        self.received_start = threading.Semaphore(value=0)
        self.done_playing = threading.Event()
        self.stopped = threading.Event()
        self.playback_resumed = threading.Condition()
        self.groover_lock = threading.Lock()


    def play(self, )-> None:
        try:
            """
            Play the given tune with the given groover.
    
            :param loeric_id: the id of the current LOERIC istance
            :param groover: the groover object
            :param tune: the tune object
            :param sync_port_out: the MIDI port for synchronization
            :param kwargs: the performance arguments
            """
            # create player
            self.player = pl.Player(
                tempo=self.groover.tempo,
                key_signature=self.tune.key_signature,
                time_signature=self.tune.time_signature,
                save=False,
                verbose=False,
                midi_out=out,
            )

            # wait for start
            self.received_start.acquire()
            self.player.init_playback()

            # repeat as specified
            # iterate over messages
            while True:
                if stopped.is_set():
                    self.player.reset()
                    with self.playback_resumed:
                        self.playback_resumed.wait()
                    self.player.init_playback()
                message = self.groover.next_event()
                if message is None:
                    break

                if message.type == "sysex":
                    print(f"Repetition {message.data[0] + 1}/{kwargs['repeat']}")
                    continue
                # perform notes
                elif lu.is_note(message):
                    # make the groover play the messages
                    new_messages = self.groover.perform(message)
                # keep meta messages intact
                else:
                    if message.type == "songpos":
                        if sync_port_out is not None:
                            sync_port_out.send(message)
                            # print(f"{loeric_id} SENT {message.pos} ({time.time()})")
                        new_messages = []
                    else:
                        new_messages = [message]
                # play
                self.player.play(new_messages)

            # play an end note
            if not kwargs["no_end_note"]:
                self.groover.reset_contours()
                self.groover.advance_contours()
                self.player.play(self.groover.get_end_notes())

            self.done_playing.set()
            print("Player thread terminated.")

        except Exception as e:
            # stop sync thread
            self.done_playing.set()
            print("Player thread terminated.")
            raise e


    def sync_thread(
            self, sync_port_in: mido.ports.BaseInput, out: mido.ports.BaseOutput
    ) -> None:
        """
        Handle MIDI start, stop, songpos and tempo messages.
        """
        global stopped
        while not self.done_playing.is_set():
            msg = sync_port_in.receive(block=True)
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
                if stopped.is_set():
                    self.groover.jump_to_pos(msg.pos)
                else:
                    print(f"Ignoring JUMP because playback is active.")
            elif msg.type == "start":
                self.received_start.release(n=2)
                print("Received START.")
            elif msg.type == "stop":
                stopped.set()
                print("Received STOP.")
            elif msg.type == "continue":
                stopped.clear()
                with self.playback_resumed:
                    self.playback_resumed.notify_all()
                print("Received CONTINUE.")

        print("Sync thread terminated.")


    def check_midi_control(
            self, control2contour: dict[int, str]
    ) -> Callable[[], None]:
        """
        Returns a function that associates a contour name (values) for every MIDI control number in the dictionary (keys) and updates the groover accordingly.
        The value of the contour will be the control value mapped in the interval [0, 1].

        :param groover: the groover object.
        :param control2contour: a dictionary of control numbers associated to contour names.

        :return: a callback function that will check for the given values.
        """

        def callback(msg):
            if lu.is_note(msg):
                pass
            for event_number in control2contour:
                if msg.is_cc(event_number):
                    contour_name = control2contour[event_number]
                    value = msg.value / 127
                    groover.set_contour_value(contour_name, value)
                    print(f'"\x1B[0K"{contour_name}:\t{round(value, 2)}', end="\r")

        return callback
