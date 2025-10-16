import faulthandler
import time
import os
import threading
from collections import defaultdict
from enum import Enum
from os.path import splitext
from random import randint
from typing import Optional

import pyaudio as pa
import mido
from mido import Message
from mido.ports import BaseOutput, BaseInput, EchoPort

from loeric import loeric_utils as lu
from loeric.groover import Groover
from loeric.player import Player
import loeric.server as ls
import loeric.tune as tu
import loeric.listeners.playalong as lp

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
    ):
        self.name = name
        self.id = loeric_id
        self._instrument = instrument
        self._midi_out = midi_out
        self._droning = True

        self.sync = EchoPort(f"LOERIC Sync #{loeric_id}#")
        self.seed = randint(0, 1000000)
        self.thread = threading.Thread()
        self._tempo = 140

        self._intensity_control = 49
        self._human_impact_control = 50
        self._invert = False
        self._responsiveness = 0.8

        self._midi_in = None
        self._device_index = None

        self._slow_start = False
        self._slow_end = False
        self._tune = tune

        self.create_all()

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

    def set_input_audio_device(self, device_index):
        self._device_index = device_index
        if self._device_index is not None:
            self.start_listener()

    def start_listener(self):
        p = pa.PyAudio()
        info = p.get_device_info_by_index(self._device_index)
        name = info["name"]
        print(f"Connecting to device {self._device_index}: {name}")

        # create listening thread
        self._listener_thread = lp.ListenerThread(
            sample_rate=int(info["defaultSampleRate"]),
            chunk_per_sec=10,
            device_index=self._device_index,
            num_channels=1,
            selected_channels=[1],
        )
        self._listener_thread.open_stream()

        # create audio monitor
        audio_monitor = lp.AudioMonitor()

        # create playback thread
        self._control_thread = lp.PlayerThread(self._invert)

        # go until midi is playing
        l = threading.Thread(
            target=self._listener_thread.listen,
            args=(audio_monitor, self._responsiveness),
        )

        def callback(perc):
            self.groover.set_control_value(self._intensity_control, perc)
            for i in range(len(self._controls)):
                if self._controls[i]["control"] == self._intensity_control:
                    self._controls[i]["value"] = perc

        p = threading.Thread(
            target=self._control_thread.send_control_loop,
            args=[audio_monitor, callback],
        )

        l.start()
        p.start()

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

    @property
    def slow_start(self):
        return self._slow_start

    @slow_start.setter
    def slow_start(self, value):
        self._slow_start = value
        self.create_all()

    @property
    def slow_end(self):
        return self._slow_end

    @slow_end.setter
    def slow_end(self, value):
        self._slow_end = value
        self.create_all()

    def set_tempo(self, tempo):
        self._tempo = tempo
        self.groover.set_tempo(tempo)

    def create_all(self):

        self._listener_thread = None
        self._control_thread = None
        ################### configs ###########################
        config = self.tune.config

        additional_configs = [
            f"{ls.server.specific_configs_path}/instrument/{self.instrument.lower()}.json"
        ]
        if not os.path.isfile(config):
            print(f"Could not load {config}")
            additional_configs.extend(
                [
                    f"{ls.server.general_configs_path}/tune_type/{self.tune.tune_type}.json",
                    # f"{ls.server.specific_configs_path}/musicians/{self.name.lower()}.json",
                ]
            )
            config = None

        ################### groover ###########################

        self.groover = Groover(
            self.tune,
            seed=self.seed,
            config_file=config,
            intensity_control=self._intensity_control,
            human_impact_control=self._human_impact_control,
            additional_configs=[
                file for file in additional_configs if os.path.isfile(file)
            ],
            loeric_id=self.id,
            bpm=self._tempo,
            human_impact=1,
            slow_start=self._slow_start,
            slow_end=self._slow_end,
            verbose=3,
        )
        ################### controls ###########################

        config = self.groover._config["control_2_contour"]
        self._controls = [
            {
                "name": " ".join(c.split("_")).title(),
                "control": config[c]["control"],
                "value": 0.5,
            }
            for c in config
        ]

        ################### output ###########################

        midi_output = None
        if self._midi_out is None:
            midi_output = mido.open_output(f"LOERIC out #{self.id}#", virtual=True)
        else:
            midi_output = self._midi_out

        midi_output.reset()

        ################### input ###########################

        if self._midi_in is not None:

            def callback(msg):
                if msg.is_cc():
                    for i in range(len(self._controls)):
                        if self._controls[i]["control"] == msg.control:
                            self._controls[i]["value"] = msg.value / 127

                callback.handle_midi(msg)

            callback.handle_midi = self.groover.check_midi_control()
            self._midi_in.callback = callback

        ################### player ###########################

        # create player
        self.player = Player(
            tempo=self.groover.tempo,
            key_signature=self.tune.key_signature,
            time_signature=self.tune.time_signature,
            save=False,
            midi_out=midi_output,
            song_start_time=self.tune.times[0].eighth_duration,
        )

    @property
    def midi_in(self):
        return self._midi_in

    @midi_in.setter
    def midi_in(self, midi_in):
        self._midi_in = midi_in

        if midi_in is None:
            return

        def callback(msg):
            if msg.is_cc():
                for i in range(len(self._controls)):
                    if self._controls[i]["control"] == msg.control:
                        self._controls[i]["value"] = msg.value / 127

            callback.handle_midi(msg)

        callback.handle_midi = self.groover.check_midi_control()

        self._midi_in.callback = callback

    @property
    def midi_out(self):
        return self._midi_out

    @midi_out.setter
    def midi_out(self, out):
        self._midi_out = out
        self.player.set_midi_out(out)

    def stop(self):
        self.groover.jump_to_pos(0)
        if self.player is not None:
            self.player.set_song_time(self.groover._tune.position_time(0))
        if self._midi_out is not None:
            self._midi_out.panic()

    def stop_threads(self):
        if self._listener_thread is not None:
            self._listener_thread.stop = True
        if self._control_thread is not None:
            self._control_thread.stop = True

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

            int_value = 0.5
            hi_value = 0.5

            if self._midi_in is None and self._device_index is None:
                hi_value = 0

            for i in range(len(self._controls)):
                if self._controls[i]["control"] == self._intensity_control:
                    self._controls[i]["value"] = int_value
                    self.groover.set_control_value(self._intensity_control, int_value)
                elif self._controls[i]["control"] == self._human_impact_control:
                    self._controls[i]["value"] = hi_value
                    self.groover.set_control_value(self._human_impact_control, hi_value)

            player_t = threading.Thread(
                target=self.player_loop, args=[self.player, self.groover]
            )
            player_t.start()

            # wait for start
            _play_event.wait()
            self.player.init_playback()
            self.player.reset_song_time()

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

            print("Player thread terminated.")

        except Exception as e:
            # stop sync thread
            _update(State.STOPPED)
            print("Player thread terminated.")
            raise e

    def __json__(self):
        out = self._midi_out
        if isinstance(self._midi_out, BaseOutput):
            out = self._midi_out.name
        midi_in = None
        if isinstance(self._midi_in, BaseInput):
            midi_in = self._midi_in.name
        return {
            "id": self.id,
            "name": self.name,
            "midiOut": out,
            "midiIn": midi_in,
            "audioIn": f"audioIn:{self._device_index}",
            "instrument": self.instrument,
            "controls": self._controls,
            "droning": self.groover._config["drone"]["active"],
            "slow_start": self.groover._config["tempo_control"]["slow_start"],
            "slow_end": self.groover._config["tempo_control"]["slow_end"],
            "transpose": self.groover._config["values"]["transpose"],
        }
