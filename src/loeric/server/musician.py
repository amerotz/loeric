import faulthandler
import time
import os
import threading
from enum import Enum
from random import randint

import pyaudio as pa
import mido
from mido.ports import BaseOutput, BaseInput, EchoPort

from loeric.groover import Groover
from loeric.player import Player
import loeric.tune as tu
import loeric.loeric_utils as lu
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
        synth_sound: str,
        midi_out: BaseOutput | None = None,
    ):
        self.name = name
        self.id = loeric_id
        self._synth_sound = synth_sound
        self._midi_out = midi_out
        self._droning = True

        self.sync = EchoPort(f"LOERIC Sync #{loeric_id}#")
        self.seed = randint(0, 1000000)
        self.thread = threading.Thread()

        self._intensity_control = 49
        self._human_impact_control = 50
        self._invert = False
        self._responsiveness = 0.8

        self._midi_in = None
        self._device_index = None

        self._slow_start = False
        self._slow_end = False
        self._tunes = []
        self._groovers = []
        self._controls = []
        self._tempos = []
        self._tune_index = 0

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
            self.stop_threads()
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
        t = threading.Thread(
            target=self._listener_thread.listen,
            args=(audio_monitor, self._responsiveness),
        )

        def callback(perc):
            self._groovers[self._tune_index].set_control_value(
                self._intensity_control, perc
            )
            for i in range(len(self._controls[self._tune_index])):
                if (
                    self._controls[self._tune_index][i]["control"]
                    == self._intensity_control
                ):
                    self._controls[self._tune_index][i]["value"] = perc

        p = threading.Thread(
            target=self._control_thread.send_control_loop,
            args=[audio_monitor, callback],
        )

        t.start()
        p.start()

    @property
    def midi_channels(self):
        return [
            self._groovers[self._tune_index]._midi_channel,
            *self._groovers[self._tune_index]._drone_midi_channels,
        ]

    @property
    def instrument(self):
        return self._synth_sound.name

    @instrument.setter
    def instrument(self, value):
        self._synth_sound = value
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
        current_tempo = self._tempos[self._tune_index]
        tempo_ratio = tempo / current_tempo
        for i in range(len(self._tunes)):
            self._tempos[i] = current_tempo * tempo_ratio
            self._groovers[i].set_tempo(current_tempo * tempo_ratio)

    def create_all(self):

        self._listener_thread = None
        self._control_thread = None
        ################### configs ###########################

        self._groovers = []
        self._controls = []
        self._tune_index = 0
        for i, tune in enumerate(self._tunes):

            additional_configs = [
                self._synth_sound.config,
                f"{lu.general_configs_path}/tune_type/{tune.tune_type}.json",
                tune.config,
            ]

            for file in additional_configs:
                if not os.path.isfile(file):
                    print(f"[MSCN] Could not find configuration '{file}'.")

            ################### groover ###########################

            groover = Groover(
                tune,
                seed=self.seed,
                config_file=None,
                intensity_control=self._intensity_control,
                human_impact_control=self._human_impact_control,
                additional_configs=[
                    file for file in additional_configs if os.path.isfile(file)
                ],
                loeric_id=self.id,
                bpm=self._tempos[i],
                human_impact=1,
                slow_start=self._slow_start and i == 0,
                slow_end=self._slow_end and i == len(self._tunes) - 1,
                verbose=3,
            )
            self._groovers.append(groover)
            ################### controls ###########################

            self._controls.append(
                [
                    {
                        "name": " ".join(c.split("_")).title(),
                        "control": groover._config["control_2_contour"][c]["control"],
                        "value": 0.5,
                    }
                    for c in groover._config["control_2_contour"]
                ]
            )

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
                    for i in range(len(self._controls[self._tune_index])):
                        if (
                            self._controls[self._tune_index][i]["control"]
                            == msg.control
                        ):
                            self._controls[self._tune_index][i]["value"] = (
                                msg.value / 127
                            )

                callback.handle_midi(msg)

            callback.handle_midi = self._groovers[self._tune_index].check_midi_control()
            self._midi_in.callback = callback

        ################### player ###########################

        # create player
        self.player = Player(
            tempo=self._groovers[self._tune_index].tempo,
            key_signature=self._tunes[self._tune_index].key_signature,
            time_signature=self._tunes[self._tune_index].time_signature,
            save=False,
            midi_out=midi_output,
            song_start_time=self._tunes[self._tune_index].times[0].eighth_duration,
        )

    @property
    def groover(self):
        return self._groovers[self._tune_index]

    @property
    def tune(self):
        return self._tunes[self._tune_index]

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
                for i in range(len(self._controls[self._tune_index])):
                    if self._controls[self._tune_index][i]["control"] == msg.control:
                        self._controls[self._tune_index][i]["value"] = msg.value / 127

            callback.handle_midi(msg)

        callback.handle_midi = self._groovers[self._tune_index].check_midi_control()

        self._midi_in.callback = callback

    @property
    def midi_out(self):
        return self._midi_out

    @midi_out.setter
    def midi_out(self, out):
        self._midi_out = out
        self.player.set_midi_out(out)

    def stop(self):
        self._groovers[self._tune_index].jump_to_pos(0)
        if self.player is not None:
            self.player.set_song_time(
                self._groovers[self._tune_index]._tune.position_time(0)
            )
        if self._midi_out is not None:
            self._midi_out.panic()

    def stop_threads(self):
        if self._listener_thread is not None:
            self._listener_thread.stop = True
        if self._control_thread is not None:
            self._control_thread.stop = True

    def ready(self) -> None:
        if _state == State.STOPPED:
            self.thread = threading.Thread(target=self.__play)
            self.thread.start()

            self.player_t = threading.Thread(
                target=self.player_loop,
                args=[self.player, self._groovers[self._tune_index]],
            )
            self.player_t.start()

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

            int_value = 0.5
            hi_value = 0.5

            if self._midi_in is None and self._device_index is None:
                hi_value = 0

            for i in range(len(self._controls[self._tune_index])):
                if (
                    self._controls[self._tune_index][i]["control"]
                    == self._intensity_control
                ):
                    self._controls[self._tune_index][i]["value"] = int_value
                    self._groovers[self._tune_index].set_control_value(
                        self._intensity_control, int_value
                    )
                elif (
                    self._controls[self._tune_index][i]["control"]
                    == self._human_impact_control
                ):
                    self._controls[self._tune_index][i]["value"] = hi_value
                    self._groovers[self._tune_index].set_control_value(
                        self._human_impact_control, hi_value
                    )

            # wait for start
            _play_event.wait()

            # iterate over messages
            for i in range(len(self._tunes)):

                self._tune_index = i
                self.tempo = self._groovers[self._tune_index]

                ############# PREAMBLE ###############
                self.player.init_playback()
                self.player.reset_song_time(
                    song_time=self._groovers[self._tune_index]
                    ._tune.times[0]
                    .eighth_duration,
                )
                ############# PREAMBLE ###############

                while True:

                    if _state == State.PAUSED:
                        self.player.reset()
                        _play_event.wait()
                        self.player.init_playback()
                    elif _state == State.STOPPED:
                        break

                    original_message = self._groovers[self._tune_index].next_event()

                    if original_message is None:
                        self._groovers[self._tune_index].reset()
                        break

                    new_messages = []
                    # perform notes
                    if original_message.is_note:
                        # make the groover play the messages
                        midi_headers, new_messages = self._groovers[
                            self._tune_index
                        ].perform(original_message)
                    # keep meta messages intact
                    else:
                        if isinstance(original_message, tu.SongPosition):
                            for msg in original_message.to_midi():
                                self.sync.send(msg)
                            print(
                                f"[INFO]\t{self._groovers[self._tune_index].loeric_id} SENT {original_message.position} ({time.time()})"
                            )
                        elif isinstance(original_message, tu.Repetition):
                            print(original_message)
                        elif (
                            isinstance(original_message, tu.KeySignature)
                            and not self._tunes[self._tune_index].forced_key
                        ):
                            print(f"[INFO]\tChanging key. {original_message}")
                            self._groovers[self._tune_index]._tune.set_key_signature(
                                original_message
                            )
                        elif isinstance(original_message, tu.Chord):
                            if original_message.is_user:
                                print(f"[INFO]\tForcing chord: {original_message}")
                            else:
                                print(f"[INFO]\tPlaying chord: {original_message}")
                            self._groovers[self._tune_index]._tune.set_chord(
                                original_message
                            )
                        else:
                            print(
                                f"[WARN]\tUnknown message type {type(original_message)}."
                            )

                        midi_headers = original_message.to_midi(absolute_time=True)

                    self.player.set_tempo_scale(
                        self._groovers[self._tune_index].tempo_scale
                    )
                    self.player.add_midi(midi_headers)
                    self.player.add_notes(new_messages)

                    self.player.wake_me_up_at(
                        original_message.time + original_message.duration
                    )

                    self.player.has_reached_wake_time.wait()

                if self._groovers[self._tune_index].do_end_note:
                    self._groovers[self._tune_index].reset()
                    self._groovers[self._tune_index].advance_contours()
                    end_notes = self._groovers[self._tune_index].get_end_notes()
                    self.player.add_notes(end_notes)

                    self.player.wake_me_up_at(
                        end_notes[-1].time + end_notes[-1].duration
                    )
                else:
                    self.player.wake_me_up_at(
                        self._groovers[self._tune_index].performance_time
                    )

                self.player.has_reached_wake_time.wait()
                self.player.reset()

            _update(State.STOPPED)

            while self.player_t.is_alive():
                self.player_t.join(1)

            print("Player thread terminated.")

        except Exception as e:
            # stop sync thread
            _update(State.STOPPED)
            print("Player thread terminated.")
            raise e

    def set_transpose(self, semitones):
        for i in range(len(self._groovers)):
            self._groovers[i].set_transpose(semitones)

    def set_control_value(self, control, value):
        for i in range(len(self._groovers)):
            self._groovers[i].set_control_value(control, value)
            for j in range(len(self._controls[i])):
                if self._controls[i][j]["control"] == control:
                    self._controls[i][j]["value"] = value

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
            "controls": self._controls[self._tune_index],
            "droning": self._groovers[self._tune_index]._config["drone"]["active"],
            "slow_start": self._groovers[self._tune_index]._config["tempo_control"][
                "slow_start"
            ],
            "slow_end": self._groovers[self._tune_index]._config["tempo_control"][
                "slow_end"
            ],
            "transpose": self._groovers[self._tune_index]._config["values"][
                "transpose"
            ],
        }
