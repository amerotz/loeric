"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import asyncio
import faulthandler
import json
import os
import random
import threading

import mido
import pyaudio as pa

import loeric.groover as gr
import loeric.listeners.playalong as lp
import loeric.loeric_utils as lu
import loeric.player as pl
import loeric.server.server as lss


faulthandler.enable()


# bad code goes here


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
        midi_out: mido.ports.BaseOutput | None = None,
    ):
        self.name = name
        self.id = loeric_id
        self._synth_sound = synth_sound
        self._midi_out = midi_out
        self._droning = True

        self.seed = random.randint(0, 1000000)
        self.thread = threading.Thread()
        self._listener_thread = threading.Thread()
        self._listener = None
        self._controller = None
        self._controller_thread = threading.Thread()
        self.player_t = threading.Thread()

        self._intensity_control = 49
        self._human_impact_control = 50
        self._invert = False
        self._responsiveness = 0.8
        self.connected_clients = set()

        self._midi_in = None
        self._device_index = None

        self._slow_start = False
        self._slow_end = False
        self._tunes = []
        self._groovers = []
        self._controls = []
        self._tempos = []
        self._tune_index = 0
        self._transpose = 0
        self.playing = False

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # start unpaused

        self.thread = None
        self.player_t = None

    def player_loop(self):
        try:
            print("[INFO]\tPlayer thread started.")
            while not self._stop_event.is_set():

                # If paused then block indefinitely
                while (
                    self.current_groover.stopped.is_set()
                    and not self._stop_event.is_set()
                ):
                    self.player.reset()
                    self.current_groover.playback_resumed.wait()

                    # If stop happened while paused then exit
                    if self._stop_event.is_set():
                        break

                    self.player.init_playback()

                # Normal playback
                self.player.play_next()

        finally:
            print("[INFO]\tPlayer thread terminated.")

    def set_input_audio_device(self, device_index):
        self.stop_threads()
        self._device_index = device_index
        if self._device_index is not None:
            self.start_listener()

    def start_listener(self):
        p = pa.PyAudio()
        info = p.get_device_info_by_index(self._device_index)
        name = info["name"]
        print(f"Connecting to device {self._device_index}: {name}")

        # create listening thread
        self._listener = lp.ListenerThread(
            sample_rate=int(info["defaultSampleRate"]),
            chunk_per_sec=10,
            device_index=self._device_index,
            num_channels=1,
            selected_channels=[1],
        )
        self._listener.open_stream()

        # create audio monitor
        audio_monitor = lp.AudioMonitor()

        # create playback thread
        self._controller = lp.PlayerThread(self._invert)

        # go until midi is playing
        self._listener_thread = threading.Thread(
            target=self._listener.listen,
            args=(audio_monitor, self._responsiveness),
        )

        self._async_loop = asyncio.get_event_loop()

        def callback(perc):
            message = {"controls": {}}
            if self.current_groover is not None:
                self.current_groover.set_control_value(self._intensity_control, perc)
                for i in range(len(self.current_controls)):
                    number = self.current_controls[i]["control"]
                    name = self.current_controls[i]["name"]
                    if number == self._intensity_control:
                        self.current_controls[i]["value"] = perc
                        message["controls"][name] = perc
            message["intensity"] = float(perc)
            for ws in self.connected_clients:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps(message)), self._async_loop
                )

        self._controller_thread = threading.Thread(
            target=self._controller.send_control_loop,
            args=[audio_monitor, callback],
        )

        self._listener_thread.start()
        self._controller_thread.start()

    @property
    def midi_channels(self):
        return [
            self.current_groover._midi_channel,
            *self.current_groover._drone_midi_channels,
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
    def invert(self):
        return self._invert

    @invert.setter
    def invert(self, value):
        self._invert = value
        self._controller.invert = value

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

        self._transpose = 0
        ################### configs ###########################

        self._groovers = []
        self._controls = []
        self._groover_transposes = []
        self._tune_index = 0
        for i, tune in enumerate(self._tunes):

            additional_configs = [
                self._synth_sound.config,
                lu.general_configs_path / "tune_type" / f"{tune.tune_type}.json",
                tune.config,
            ]

            for file in additional_configs:
                if not os.path.isfile(file):
                    print(f"[MSCN] Could not find configuration '{file}'.")

            ################### groover ###########################

            groover = gr.Groover(
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
            self._groover_transposes.append(groover.transpose)

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

        self._async_loop = asyncio.get_event_loop()
        if self._midi_in is not None:
            self._midi_in.callback = self._midi_callback

        ################### player ###########################

        # create player
        self.player = pl.Player(
            tempo=self.current_groover.tempo,
            key_signature=self.current_tune.key_signature,
            time_signature=self.current_tune.time_signature,
            save=False,
            midi_out=midi_output,
            song_start_time=self.current_tune.times[0].eighth_duration,
        )

        # create grover and player threads
        # and start them
        self.ready()

    def _midi_callback(self, msg):
        if msg.is_cc():
            value = msg.value / 127
            message = {"controls": {}}
            for i in range(len(self.current_controls)):
                number = self.current_controls[i]["control"]
                name = self.current_controls[i]["name"]
                if number == msg.control:
                    self.current_controls[i]["value"] = value
                    message["controls"][name] = value
            # send ws to client
            for ws in self.connected_clients:
                asyncio.run_coroutine_threadsafe(
                    ws.send_text(json.dumps(message)), self._async_loop
                )

            self.current_groover.check_midi_control()(msg)

    @property
    def current_groover(self):
        if len(self._groovers) == 0:
            return None
        return self._groovers[self._tune_index]

    @property
    def current_tune(self):
        if len(self._tunes) == 0:
            return None
        return self._tunes[self._tune_index]

    @property
    def current_controls(self):
        if len(self._controls) == 0:
            return None
        return self._controls[self._tune_index]

    @property
    def current_transpose(self):
        if len(self._groover_transposes) == 0:
            return None
        return self._groover_transposes[self._tune_index]

    @property
    def midi_in(self):
        return self._midi_in

    @midi_in.setter
    def midi_in(self, midi_in):
        self.stop_threads()
        if self._midi_in is not None:
            self._midi_in.callback = None
            self._midi_in.close()
        self._midi_in = midi_in

        if midi_in is None:
            return

        self._async_loop = asyncio.get_event_loop()
        self._midi_in.callback = self._midi_callback

    @property
    def midi_out(self):
        return self._midi_out

    @midi_out.setter
    def midi_out(self, out):
        self._midi_out = out
        self.player.set_midi_out(out)

    def stop(self):
        if self._stop_event.is_set():
            return

        self._stop_event.set()

        # Force-unblock pause state
        self.current_groover.stopped.clear()
        self.current_groover.playback_resumed.set()

        # Unblock player timing wait if needed
        self.player.has_reached_wake_time.set()

        if self.thread and self.thread.is_alive():
            self.thread.join()

        if self.player_t and self.player_t.is_alive():
            self.player_t.join()

        if self._midi_out:
            self._midi_out.panic()

        self.playing = False

    def pause(self):
        if not self.playing:
            return

        self.current_groover.playback_resumed.clear()
        self.current_groover.stopped.set()

        if self._midi_out:
            self._midi_out.panic()

        self.playing = False

    def stop_threads(self):
        if self._listener is not None:
            self._listener.stop = True

        if self._controller is not None:
            self._controller.stop = True

        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join()
            self._listener.close_stream()

        if self._controller_thread and self._controller_thread.is_alive():
            self._controller_thread.join()

    def ready(self) -> None:
        if self.thread and self.thread.is_alive():
            return

        self._stop_event.clear()
        self._pause_event.set()

        self.thread = threading.Thread(target=self._play, daemon=True)
        self.player_t = threading.Thread(target=self.player_loop, daemon=True)

    def start(self) -> None:
        if self.playing:
            return

        if not self.thread or not self.thread.is_alive():
            self.ready()

            self.current_groover.jump_to_pos(0)
            self.player.set_song_time(self.current_groover._tune.position_time(0))
            self._tune_index = 0

            self.thread.start()
            self.player_t.start()

        self._pause_event.set()
        self.current_groover.stopped.clear()
        self.current_groover.playback_resumed.set()

        self.playing = True

    def _play(
        self,
    ) -> None:
        """
        Play the given tune with the given groover.
        :param loeric_id: the id of the current LOERIC instance
        :param groover: the groover object
        :param tune: the tune object
        :param sync_port_out: the MIDI port for synchronization
        :param kwargs: the performance arguments
        """
        try:
            print("[INFO]\tGroover thread started.")

            int_value = 0.5
            hi_value = 0.5

            if self._midi_in is None and self._device_index is None:
                hi_value = 0

            for i in range(len(self.current_controls)):
                if self.current_controls[i]["control"] == self._intensity_control:
                    self.current_controls[i]["value"] = int_value
                    self.current_groover.set_control_value(
                        self._intensity_control, int_value
                    )
                elif self.current_controls[i]["control"] == self._human_impact_control:
                    self.current_controls[i]["value"] = hi_value
                    self.current_groover.set_control_value(
                        self._human_impact_control, hi_value
                    )

            # iterate over messages
            for i in range(len(self._tunes)):

                self._tune_index = i

                args = {"verbose": True}
                lu.play(
                    loop_condition=lambda: not self._stop_event.is_set(),
                    groover=self.current_groover,
                    player=self.player,
                    note_callback=None,
                    songpos_callback=None,
                    repetition_callback=None,
                    **args,
                )

        except Exception as e:
            raise e
        finally:
            self.playing = False
            self._stop_event.set()
            print("[INFO]\tGroover thread terminated.")

    def set_transpose(self, semitones):
        self._transpose = semitones
        for i in range(len(self._groovers)):
            self._groovers[i].transpose = self.current_transpose + semitones

    def set_control_value(self, control, value):
        for i in range(len(self._groovers)):
            self._groovers[i].set_control_value(control, value)
            for j in range(len(self._controls[i])):
                if self._controls[i][j]["control"] == control:
                    self._controls[i][j]["value"] = value

    def __json__(self):
        out = self._midi_out
        if isinstance(self._midi_out, mido.ports.BaseOutput):
            out = self._midi_out.name
        midi_in = None
        if isinstance(self._midi_in, mido.ports.BaseInput):
            midi_in = self._midi_in.name
        return {
            "id": self.id,
            "name": self.name,
            "midiOut": out,
            "midiIn": midi_in,
            "audioIn": f"audioIn:{self._device_index}",
            "instrument": self.instrument,
            "invert": self._invert,
            "controls": self.current_controls,
            "droning": self.current_groover._config["drone"]["active"],
            "slow_start": self._slow_start,
            "slow_end": self._slow_end,
            "transpose": self._transpose,
        }
