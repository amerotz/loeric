import faulthandler
import time
import os
import threading
from collections import defaultdict
from enum import Enum
from os.path import splitext
from random import randint
from typing import Optional

import mido
from mido import Message
from mido.ports import BaseOutput, BaseInput, EchoPort

from loeric import loeric_utils as lu
from loeric.groover import Groover
from loeric.player import Player
import loeric.server as ls
import loeric.tune as tu

faulthandler.enable()


# bad code goes here

general_configs_path = os.getcwd() + "/src/loeric/loeric_config/performance"
specific_configs_path = os.getcwd() + "/src/loeric/loeric_config/webapp_configs"


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


class Control:
    def __init__(self, name: str, control: int, value: int):
        self.name = name
        self.control = control
        self.value = value

    def __json__(self):
        return {"name": self.name, "control": self.control, "value": self.value}


class Musician:
    def __init__(
        self,
        name: str,
        loeric_id: str,
        tune: tu.Tune,
        instrument: str,
        midi_out: BaseOutput | None = None,
        midi_in: str | None = None,
    ):
        self.name = name
        self.id = loeric_id
        self._instrument = instrument
        self.midi_out = midi_out
        self.midi_in = midi_in
        self.sync = EchoPort(f"LOERIC Sync #{loeric_id}#")
        self.seed = randint(0, 1000000)
        self.thread = threading.Thread()
        self._tempo = 140
        self.control_out = ControlOutput(f"Loeric Control #{loeric_id}#", None)

        self.tune = tune

    def player_loop(self, player, groover):

        _play_event.wait()
        while True:

            if _state == State.PAUSED:
                player.reset()
                _play_event.wait()
                player.init_playback()
            elif _state == State.STOPPED:
                player.reset()
                break

            player.play_next()

    @property
    def midi_channels(self):
        return [self.groover._midi_channel, self.groover._drone_midi_channel]

    @property
    def tune(self):
        return self._tune

    @tune.setter
    def tune(self, value):
        self._tune = value
        self.create_all()

    @property
    def instrument(self):
        return self._instrument

    @instrument.setter
    def instrument(self, value):
        self._instrument = value
        self.create_all()

    def set_tempo(self, tempo):
        self._tempo = tempo
        print(tempo)
        self.groover.set_tempo(tempo)

    def create_all(self):

        additional_configs = [
            f"{general_configs_path}/tune_type/{self.tune.tune_type}.json",
            f"{general_configs_path}/instrument/{self.instrument.lower()}.json",
            f"{specific_configs_path}/tunes/{splitext(self.tune.name.lower())[0]}.json",
            f"{specific_configs_path}/musicians/{self.name.lower()}.json",
        ]
        self.groover = Groover(
            self.tune,
            seed=self.seed,
            additional_configs=[
                file for file in additional_configs if os.path.isfile(file)
            ],
            loeric_id=self.id,
            bpm=self._tempo,
            human_impact=1,
        )

        midi_output: Optional[BaseOutput] = None
        if self.midi_out is None:
            midi_output = mido.open_output(f"LOERIC out #{self.id}#", virtual=True)
        else:
            midi_output = self.midi_out

        midi_output.reset()

        # create player
        self.player = Player(
            tempo=self.groover.tempo,
            key_signature=self.tune.key_signature,
            time_signature=self.tune.time_signature,
            save=False,
            midi_out=midi_output,
        )

        self.control_out.set_groover(self.groover)

    def stop(self):
        self.groover.jump_to_pos(0)
        if self.player is not None:
            self.player.set_song_time(self.groover._tune.position_time(0))

    def ready(self) -> None:
        global _state
        if _state == State.STOPPED:
            self.thread = threading.Thread(target=self.__play)
            self.thread.start()

    def __play(
        self,
    ) -> None:
        try:
            """
            Play the given tune with the given groover.
            :param loeric_id: the id of the current LOERIC instance
            :param groover: the groover object
            :param tune: the tune object
            :param sync_port_out: the MIDI port for synchronization
            :param kwargs: the performance arguments
            """
            global _play_event, _state

            midi_input = None
            listener = None
            if self.midi_in is not None:
                if self.midi_in.startswith("audioIn:"):
                    device = int(self.midi_in.split(":")[1])
                    listener = ListenerThread(device, self.control_out, 1)
                    listener.start()
                else:
                    midi_input = mido.open_input(self.midi_in)
                    midi_input.callback = self.groover.check_midi_control()

            player_t = threading.Thread(
                target=self.player_loop, args=[self.player, self.groover]
            )
            player_t.start()

            # wait for start
            _play_event.wait()
            self.player.init_playback()

            # iterate over messages
            while True:
                # print()

                if _state == State.PAUSED:
                    self.player.reset()
                    _play_event.wait()
                    self.player.init_playback()
                elif _state == State.STOPPED:
                    break

                original_message = self.groover.next_event()

                if original_message is None:
                    self.groover.reset()
                    break

                new_messages = []
                # perform notes
                if original_message.is_note:
                    # make the groover play the messages
                    midi_headers, new_messages = self.groover.perform(original_message)
                # keep meta messages intact
                else:
                    if isinstance(original_message, tu.SongPosition):
                        for msg in original_message.to_midi():
                            self.sync.send(msg)
                        print(
                            f"[INFO]\t{self.groover.loeric_id} SENT {original_message.position} ({time.time()})"
                        )
                    elif (
                        isinstance(original_message, tu.KeySignature)
                        and not self.tune.forced_key
                    ):
                        print(f"[INFO]\tChanging key. {original_message}")
                        self.groover._tune.set_key_signature(original_message)
                    midi_headers = original_message.to_midi(absolute_time=True)

                self.player.set_tempo_scale(self.groover.tempo_scale)
                self.player.add_midi(midi_headers)
                self.player.add_notes(new_messages)

                self.player.wake_me_up_at(
                    original_message.time + original_message.duration / 2
                )

                self.player.has_reached_wake_time.wait()

            if self.groover.do_end_note:
                self.groover.reset()
                self.groover.advance_contours()
                end_notes = self.groover.get_end_notes()
                self.player.add_notes(end_notes)

                self.player.wake_me_up_at(end_notes[-1].time + end_notes[-1].duration)
            else:
                self.player.wake_me_up_at(self.groover.performance_time)

            self.player.has_reached_wake_time.wait()

            _update(State.STOPPED)

            while player_t.is_alive():
                player_t.join(1)

            if listener is not None:
                listener.stop = True

            if midi_input is not None:
                midi_input.close()
                if midi_input.closed:
                    print("Closed MIDI input.")

            # make sure to turn off all notes
            """
            if midi_output is not None:
                for i in range(127):
                    midi_output.send(
                        mido.Message("note_off", velocity=0, note=i, time=0)
                    )
                midi_output.reset()
                # midi_output.close()
                if midi_output.closed:
                    print("Closed MIDI output.")
            """

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
        return {
            "id": self.id,
            "name": self.name,
            "midiOut": out,
            "midiIn": self.midi_in,
            "instrument": self.instrument,
            "controls": list(map(lambda m: m.__json__(), self.control_out.controls)),
        }


class ControlOutput(BaseOutput):
    def __init__(self, name: str, groover: Groover | None, **kwargs):
        self.groover = groover
        self.controls = [Control("Volume", 7, 127), Control("Intensity", 21, 127)]
        BaseOutput.__init__(self, name=name, **kwargs)

    def set_groover(self, groover: Groover | None):
        self.groover = groover
        if groover is not None:
            contours = self.groover._config.get("control_2_contour")
            grouped = defaultdict(list)
            for key, val in sorted(contours.items()):
                grouped[val].append(key)

            self.controls = [self.controls[0]]
            for control, values in grouped.items():
                name = values[0]
                value = int(self.groover._contour_values[name] * 127)
                if len(values) > 1:
                    if all("_human_impact" in x for x in values):
                        name = "Human Impact"
                    else:
                        name = "Intensity"
                self.controls.append(Control(name, control, value))
