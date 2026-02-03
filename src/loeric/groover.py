import mido
import os
import jsonmerge
import copy
import random
import json
import threading
import time
import numpy as np
import music21 as m21

from collections import defaultdict
from collections.abc import Callable


from loeric import tune as tu
from loeric import contour as cnt
from loeric import loeric_utils as lu
from loeric.loeric_config import loeric_config as lc


class UnknownContourError(Exception):
    """Raised if trying to set a contour whose name does not correspond to any of the Groover's contours."""

    pass


class Groover:
    """The class responsible for playback, ornamentation and human interaction."""

    def __init__(
        self,
        tune: tu.Tune,
        bpm: int = None,
        midi_channel: int = 0,
        transpose: int = 0,
        human_impact: float = 0,
        seed: int = 42,
        config_file: str = None,
        additional_configs: list = [],
        intensity_control: int = 1,
        human_impact_control: int = 11,
        syncing: bool = False,
        plot=None,
        slow_start=False,
        slow_end=False,
        do_end_note=False,
        verbose=0,
        loeric_id: str = None,
    ):
        """
        Initialize the groover class by setting user-defined parameters and creating the contours.
        Any parameters set on class instatiation that are also present in the configuration file will be overwritten. To preserve command line arguments, omit the corresponding fields from the  configuration file.

        :param tune: the tune that will be performed.
        :param bpm: the user-defined tempo in bpm for the tune.
        :param midi_channel: the midi output channel for all note messages. Drone messages will be sent on midi_channel + 1 if not specified otherwise in the configuration.
        :param transpose: the number of semitones by which to transpose the tune.
        :param human_impact: the initial weight of the external control signal.
        :param seed: the random seed of the performance.
        :param config_file: the path to the configuration file (must be a JSON file).
        :param intensity_control: the MIDI CC to use for intensity.
        :param human_impact_control: the MIDI CC to use for human impact.
        :param syncing: whether or not synchronization with multiple LOERIC istances is active.
        :param plot: the contour to plot before playback.
        :param slow_start: start the performance at a slower tempo.
        :param slow_end: end the performance at a slower tempo.
        """

        self._plot = plot
        self._verbose = verbose
        self._slow_start = slow_start
        self._slow_end = slow_end
        self.loeric_id = loeric_id

        # to synchronize
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.playback_resumed = threading.Event()
        self.skip_repetition = False

        # tune
        self._tune = tune
        self._tempo = self._tune._tempos[0]

        # offset for messages after ornaments
        self._eighths_to_skip = 0

        # index to yield note events
        # will be increased before yielding message
        self._note_index = -1
        self._note_index_lock = threading.RLock()
        self._performance_time = tu.TimeDelta(eighth_duration=0)

        self._initial_human_impact = human_impact
        self._syncing = syncing

        # only define command line values
        # rest is part of loeric_config/base.json
        self._config = {
            "variables": {
                "var_drone_midi_channel": midi_channel + 1,
                "var_notes_per_bar": [self._tune.time_signature.beat_count],
            },
            "contours": {
                "drone": {
                    "human_impact_scale": human_impact,
                },
                "velocity": {
                    "human_impact_scale": human_impact,
                },
                "ornament": {
                    "human_impact_scale": human_impact,
                },
            },
            "values": {
                "midi_channel": midi_channel,
                "transpose": transpose,
                "seed": seed,
                "do_end_note": do_end_note,
            },
            "tempo_control": {
                "tempo_warp_bpms": 10,
                "bpm": bpm,
                "slow_start": slow_start,
                "slow_end": slow_end,
                "slow_start_bars": 3,
                "slow_end_bars": 2,
                "slow_affected_contours": ["velocity", "ornament", "tempo", "drone"],
            },
            "control_2_contour": {
                "intensity": {
                    "control": intensity_control,
                    "contours": [
                        "velocity_intensity",
                        "tempo_intensity",
                        "ornament_intensity",
                        "legato_intensity",
                        "drone_intensity",
                    ],
                },
                "human_impact": {
                    "control": human_impact_control,
                    "contours": [
                        "velocity_human_impact",
                        "tempo_human_impact",
                        "ornament_human_impact",
                        "legato_human_impact",
                        "drone_human_impact",
                    ],
                },
            },
            "harmony": {
                "chords_per_bar": self._tune.time_signature.beat_count,
                "allowed_chords": f"{self._tune.key_signature.mode}_allowed_chords",
            },
            "drone": {},
        }

        # merge base configuration with command line values
        dir_path = os.path.dirname(os.path.realpath(__file__))
        with open(f"{dir_path}/loeric_config/performance/base.json", "r") as f:
            base_config = json.load(f)
            self._config = jsonmerge.merge(base_config, self._config)

        # use external configuration if specified
        # the configuration file overwrites any defaults
        # specified by command line
        if config_file is not None:

            with open(config_file, "r") as f:
                config_file = json.load(f)

                self._config = lc.merge_configs(self._config, config_file)

        # add additional configuration bits
        for config_file in additional_configs:

            print(f"[GRVR] Using additional config {os.path.basename(config_file)}")
            with open(config_file, "r") as f:
                config_file = json.load(f)

                self._config = lc.merge_configs(self._config, config_file)

        config_hash = int(hash(str(config_file))) % 2**31
        self._config["values"]["seed"] = config_hash + seed

        # compile variables by copying them explicitly
        if "variables" in self._config:
            variables = self._config["variables"]

            del self._config["variables"]

            # turn config into string
            dict_string = json.dumps(self._config)

            for name, value in variables.items():
                dict_string = dict_string.replace(f'"{name}"', json.dumps(value))

            self._config = json.loads(dict_string)

        with open(f"{dir_path}/last_config.json", "w") as f:
            json.dump(self._config, f)

        # generate all parameter settings and contours
        self._instantiate()

    def _instantiate(self):
        """
        Generate all parameter settings following the current configuration.
        """

        # random seed
        random.seed(self._config["values"]["seed"])
        np.random.seed(self._config["values"]["seed"])

        tu.BEND_UP = self._config["values"]["bend_up_semitones"]
        tu.BEND_DOWN = self._config["values"]["bend_down_semitones"]

        tu.BEND_UP = self._config["values"]["bend_up_semitones"]
        tu.BEND_DOWN = self._config["values"]["bend_down_semitones"]

        self._midi_channel = self._config["values"]["midi_channel"]
        # collect all drone midi channels
        self._drone_midi_channels = []
        for d in self._config["drone"]["drone_sets"]:
            ch = self._config["drone"]["drone_sets"][d]["midi_channel"]
            if ch not in self._drone_midi_channels:
                self._drone_midi_channels.append(ch)

        # set parameters
        if self._config["tempo_control"]["bpm"] is None:
            self._user_tempo = self._tune._tempos[0]
        else:
            self._user_tempo = tu.Tempo(qpm=self._config["tempo_control"]["bpm"])
        self._max_ornament_length = 0
        for o in self._config["ornamentation"]:
            self._max_ornament_length = max(
                self._max_ornament_length, self._config["ornamentation"][o]["length"]
            )

        # legato
        self._legato_amount = (
            self._config["legato"]["max"] - self._config["legato"]["min"]
        )

        # droning
        self._active_pedals = []
        self._all_drones = np.unique(
            [
                note
                for d in self._config["drone"]["drone_sets"]
                for note in self._config["drone"]["drone_sets"][d]["notes"]
            ]
        )

        # keyswitches
        self._last_keyswitches = []

        # intonation
        self._last_recorded_intonation = 0
        self._intonation = np.zeros(127)

        # tempo sync
        self._external_tempo = None
        self._tempo_lock = threading.Lock()
        self._last_clock_time = None

        # create contours
        self._contours = {}

        for c in self._config["contours"]:
            if self._verbose in [1, 2, 3, 4]:
                print(f"[INFO]\tCreating {c} contour.")
            self._contours[c] = cnt.create_contour(
                self._tune, self._config["contours"][c]["recipe"], parent=c
            )
            if (
                "human_impact_scale" not in self._config["contours"][c]
                or self._config["contours"][c]["human_impact_scale"] is None
            ):
                self._config["contours"][c]["human_impact_scale"] = 0

        # message_length contour
        self._contours["message_length"] = cnt.MessageLengthContour()
        self._contours["message_length"].calculate(self._tune)

        self._contours["pitch_difference"] = cnt.PitchDifferenceContour()
        self._contours["pitch_difference"].calculate(self._tune)

        # pich contour
        self._contours["pitch_contour"] = cnt.PitchContour()
        self._contours["pitch_contour"].calculate(
            self._tune, savgol=False, shift=False, scale=False
        )

        self._tune.calculate_chords(
            chord_score=np.array(
                self._config["harmony"]["chord_score"],
            ),
            chords_per_bar=self._config["harmony"]["chords_per_bar"],
            allowed_chords=np.array(self._config["harmony"]["allowed_chords"]),
        )

        if (self._slow_start or self._slow_end) and self._config["tempo_control"][
            "tempo_warp_bpms"
        ] != 0:

            # create x
            x = self._tune.float_times
            x -= min(x)

            ramp_up = np.ones_like(x)
            ramp_down = np.ones_like(x)

            # create ramp
            if self._slow_start:
                B = (
                    self._tune.time_signature.eighths_per_bar
                    * self._config["tempo_control"]["slow_start_bars"]
                ).eighth_duration

                ramp_up = np.minimum(np.ones_like(x), x / B)

            if self._slow_end:
                B = (
                    self._tune.time_signature.eighths_per_bar
                    * self._config["tempo_control"]["slow_end_bars"]
                ).eighth_duration
                p = 1 / np.random.choice([2, 3])
                ramp_down = np.minimum(
                    np.ones_like(x), np.power(1 - (x - (max(x) - B)) / B, p)
                )

            # update
            for contour in self._config["tempo_control"]["slow_affected_contours"]:

                if contour not in self._config["contours"]:
                    pass

                # retrieve original contour
                data = self._contours[contour]._contour

                k_up = 0
                k_down = 0
                if contour == "velocity":
                    k_up = 0.5
                    k_down = 0.5
                elif contour == "tempo":
                    k_up = 0.5 - (
                        self._config["tempo_control"]["slow_start_percentage"]
                        * self._config["tempo_control"]["bpm"]
                    ) / (2 * self._config["tempo_control"]["tempo_warp_bpms"])
                    k_down = 0.5 - (
                        self._config["tempo_control"]["slow_end_percentage"]
                        * self._config["tempo_control"]["bpm"]
                    ) / (2 * self._config["tempo_control"]["tempo_warp_bpms"])

                cnt_ramp_down = np.multiply(ramp_down, data) + (1 - ramp_down) * k_down
                cnt_ramp_up = np.multiply(ramp_up, data) + (1 - ramp_up) * k_up

                data = np.minimum(cnt_ramp_up, cnt_ramp_down)

                # update contour
                self._contours[contour]._contour = data

        if self._plot is not None:
            import matplotlib.pyplot as plt

            x = self._tune.float_times
            plt.figure(figsize=(20, 5))
            plt.step(
                x,
                (
                    self._contours["pitch_contour"]._contour
                    - min(self._contours["pitch_contour"]._contour)
                )
                / (
                    max(self._contours["pitch_contour"]._contour)
                    - min(self._contours["pitch_contour"]._contour)
                ),
                linestyle=":",
                where="post",
            )
            plt.step(x, self._contours[self._plot]._contour, where="post", marker="x")
            plt.tight_layout()
            plt.show()

        # object holding each contour's value in a given moment
        self._contour_values = {}

        # init all contours
        for contour_name in self._config["contours"]:
            # init the human contours
            self._contour_values[f"{contour_name}_intensity"] = 0.5
            self._contour_values[f"{contour_name}_human_impact"] = self._config[
                "contours"
            ][contour_name]["human_impact_scale"]
            self._contour_values[contour_name] = 0.5

        for group in self._config["control_2_contour"].values():
            for contour_name in group["contours"]:
                # if the contour is declared in the "contours" section
                # or is used to send midi cc
                if (
                    contour_name in self._contour_values
                    or contour_name in self._config["contour_2_control"]
                    or contour_name.startswith("orn_")
                ):
                    self._contour_values[contour_name] = 0.5
                else:
                    print(
                        f"\033[38;2;255;255;0m[WARN] Contour '{contour_name}' is useless and will not be initialised.\033[0m"
                    )
        for contour_name in self._config["contour_2_control"]:
            if contour_name.split("#")[0] not in self._contour_values:
                raise Exception(
                    f"The contour '{contour_name}' in 'contour_2_control' is not declared anywhere. Make sure that it appears in 'contours' or 'control_2_contour'."
                )

    def get_control_value(self, control_num):
        """
        Read the values associated with a given control number.
        """
        val = [
            self._contour_values[c]
            for c in self._config["contour_2_control"]
            if self._config["contour_2_control"][c]["control"] == control_num
        ]
        if len(val) == 0:
            val = [0.5]
        return val

    def set_control_value(self, control_num, value):
        """
        Set a given control number to a value.
        """

        # store the raw control
        # self._contour_values[control_num] = value
        # traditional control
        for group in self._config["control_2_contour"].values():
            event_number = group["control"]
            if control_num == event_number:
                for contour_name in group["contours"]:
                    self.set_contour_value(contour_name, value)
                    # print(f'"\x1B[0K"{contour_name}:\t{round(value, 2)}', end="\r")
                    if self._verbose == 3:
                        print(
                            f"[{str(self.loeric_id)[:4]}]\t{contour_name}:\t{round(value, 2)}"
                        )

    def check_midi_control(self) -> Callable[[], None]:
        """
        Returns a function that associates a contour name (values) for every MIDI control number in the dictionary (keys) and updates the groover accordingly.
        The value of the contour will be the control value mapped in the interval [0, 1].

        :return: a callback function that will check for the given values.
        """

        def callback(msg):
            # intonation
            if lu.is_note(msg):
                self._intonation[msg.note] = self._last_recorded_intonation
                if self._verbose == 4:
                    print(f"intonation:\t\t{msg.note}")
            elif msg.type == "pitchwheel":
                self._last_recorded_intonation = msg.pitch / 8192
            else:
                pass

            if msg.is_cc():
                self.set_control_value(msg.control, msg.value / 127)

        return callback

    def advance_contours(self) -> None:
        """
        Retrieve the next value of each contour and store it for future use.
        """

        with self._note_index_lock:
            for contour_name in self._contours:
                self._contour_values[contour_name] = self._contours[contour_name].next()

        # add the human part
        for contour_name in self._config["contours"]:
            hi = (
                self._contour_values[f"{contour_name}_human_impact"]
                * self._config["contours"][contour_name]["human_impact_scale"]
            )

            intensity = self._contour_values[f"{contour_name}_intensity"]
            if self._config["contours"][contour_name]["human_impact_scale"] < 0:
                intensity = 1 - intensity
                hi = abs(hi)

            self._contour_values[contour_name] *= 1 - hi
            self._contour_values[contour_name] += hi * intensity
            """
            self._contour_values[contour_name] = np.nan_to_num(
                self._contour_values[contour_name], nan=0.5
            )
            """

    def set_contour_value(self, contour_name: str, value: float) -> None:
        """
        Set the value of a given contour to a given value until the update.

        :param contour_name: the name of the contour.
        :param value: the value to set the contour to.

        :raise groover.UnknownContourError: if the contour name does not correspond to any of the Groover's contours.
        """

        if contour_name not in self._contour_values:
            raise UnknownContourError

        self._contour_values[contour_name] = value

    def next_event(self):
        """
        Return the current event in the tune. Returns none if no event is available.
        """

        with self._note_index_lock:
            self._note_index += 1
            if self._note_index >= len(self._tune):
                return None

            event = self._tune[self._note_index]

            if event.is_note:
                # advance contours
                self.advance_contours()

            # update performance time
            self._performance_time = event.time

            return event

    def jump_to_pos(self, pos: int) -> None:
        """
        Jump to the specified song position.

        :param pos: the position to jump to.
        """

        with self._note_index_lock:
            if pos > self._tune.maximum_songpos:
                if self._verbose > 0:
                    print(
                        f"Cannot jump to position {pos} with max pos {self._tune.maximum_songpos}"
                    )
                return
            self._note_index, contour_index = self._tune.index_map[pos]
            # update performance time
            # self._performance_time = self._tune.duration_map[pos]
            # update all contours
            for contour_name in self._contours:
                self._contours[contour_name].jump(contour_index)

    def reset_clock(self) -> None:
        """
        Reset the MIDI clock to initial tempo.
        """

        self._last_clock_time = None
        with self._tempo_lock:
            self._external_tempo = None

    def set_tempo(self, tempo: float) -> None:
        """
        Set the new performance tempo.

        :param tempo: the requested tempo in bpms.
        """
        with self._tempo_lock:
            self._external_tempo = tu.Tempo(qpm=tempo)

    def set_clock(self) -> None:
        """
        Register a MIDI clock message and calculate the requested tempo.
        """
        now = time.time()
        if self._last_clock_time is not None:
            # update tempo
            # 24 clocks per quarter note
            diff = now - self._last_clock_time
            new_tempo = tu.Tempo(qpm=60 / (24 * diff))

            # if too long, reset
            if new_tempo > lu.MAX_TEMPO:
                new_tempo = None

            with self._tempo_lock:
                self._external_tempo = new_tempo
        self._last_clock_time = now

    def perform(self, message) -> list[mido.Message]:

        # work on a deepcopy to avoid side effects
        current_message = copy.deepcopy(message)
        current_message.time = self._performance_time

        if self._eighths_to_skip >= current_message.duration:
            self._eighths_to_skip -= current_message.duration
            return (
                [],
                [],
            )

        current_message._velocity = self._current_velocity
        notes = [current_message]

        # create ornaments
        if self.can_generate_ornament():
            # choose which ornament
            ornament_type = self.choose_ornament(notes[0])

            # generate it
            if ornament_type is not None:
                notes = self.generate_ornament(current_message, ornament_type)

        for note in notes:
            # channel
            note.channel = self._midi_channel

            # transpsose
            if note.is_note:
                note.transpose(self._config["values"]["transpose"])

        # add drone
        non_legato_drones = []
        original_notes = copy.deepcopy(notes)
        original_notes = [n for n in original_notes if n.is_note]

        if self._config["drone"]["active"]:

            for drone_option in self._config["drone"]["drone_sets"]:
                # pedals can't be triggered twice
                if drone_option in self._active_pedals:
                    continue

                # obtain threshold and contour values
                drone_bind_contour = self._config["drone"]["drone_sets"][drone_option][
                    "bind"
                ]
                drone_threshold = self._config["drone"]["drone_sets"][drone_option][
                    "threshold"
                ]

                drone_type = drone_option.split("#")[0]

                notes_per_bar = None
                drone_interval = current_message.duration

                if drone_type != "pedal":
                    notes_per_bar = self._current_notes_per_bar(
                        current_message, drone_option
                    )

                    # over all messages that will be output
                    drone_interval = (
                        self._tune.time_signature.eighths_per_bar / notes_per_bar
                    ).eighth_duration

                start_time = original_notes[0].time

                end_time = original_notes[-1].time + original_notes[-1].duration

                og_pitches = np.array([n.pitch for n in original_notes])
                og_times = np.array([n.time.eighth_duration for n in original_notes])
                og_velocity = np.array([n._velocity for n in original_notes])

                diff = start_time.eighth_duration % drone_interval
                times = np.arange(
                    start=start_time.eighth_duration - diff,
                    stop=end_time.eighth_duration,
                    step=drone_interval,
                )
                times = times[times % drone_interval == 0]
                times = times[times >= start_time.eighth_duration]
                times = times[times <= end_time.eighth_duration]

                idx = np.searchsorted(og_times, times, side="right") - 1
                idx = np.clip(idx, 0, len(og_times) - 1)
                pitches = og_pitches[idx]
                velocities = og_velocity[idx]

                notes_to_consider = [
                    tu.Note(pitch=p, eighth_duration=drone_interval, time=t, velocity=v)
                    for p, t, v in zip(pitches, times, velocities)
                ]

                # for each note
                for note in notes_to_consider:

                    # keep track of notes
                    drone_notes = []

                    prob = self._contours[drone_bind_contour].at(note.time)

                    # TODO remove duplicate code
                    # same as advance_contours()
                    #############################
                    hi = (
                        self._contour_values[f"{drone_bind_contour}_human_impact"]
                        * self._config["contours"][drone_bind_contour][
                            "human_impact_scale"
                        ]
                    )

                    intensity = self._contour_values[f"{drone_bind_contour}_intensity"]
                    if (
                        self._config["contours"][drone_bind_contour][
                            "human_impact_scale"
                        ]
                        < 0
                    ):
                        intensity = 1 - intensity
                        hi = abs(hi)

                    prob *= 1 - hi
                    prob += hi * intensity

                    #############################

                    # print("\t", value, drone_threshold, drone_option)
                    # value = self._contour_values[drone_bind_contour]
                    # if should be droning

                    if self._config["drone"]["probability_scale"]:
                        prob = max((prob - drone_threshold) / (1 - drone_threshold), 0)
                        can_drone = random.choices(
                            [True, False], weights=[prob, 1 - prob], k=1
                        )[0]
                    else:
                        can_drone = prob >= drone_threshold

                    if can_drone:

                        # get pitches
                        drone_pitches = self._get_drone(note.pitch, drone_option)

                        # make pedal active if pedal
                        if drone_type == "pedal" and len(drone_pitches) != 0:
                            self._active_pedals.append(drone_option)

                        # create the note events
                        drone_pitches = sorted(drone_pitches)
                        d_notes, delay = self._add_drone(
                            note, drone_pitches, drone_option, notes_per_bar
                        )
                        drone_notes.extend(d_notes)

                        # adjust delay of current note
                        removable_delay = min(delay, note.duration)
                        note.time += removable_delay
                        note.duration -= removable_delay

                    # if not pedal and config, use staccato/legato
                    # articulation with main note
                    if (
                        drone_type == "pedal"
                        or not self._config["drone"]["drone_sets"][drone_option][
                            "use_legato"
                        ]
                    ):
                        # store separately not to be affected
                        non_legato_drones.extend(drone_notes)
                    else:
                        notes.extend(drone_notes)

        for note in non_legato_drones:
            # apply swing
            note = self._apply_swing(note)

            if note.is_note:
                # change intonation
                note._pitch += self._intonation[int(note.pitch)] + self._config[
                    "values"
                ]["pitch_deviation_cents"] * 0.01 * np.random.normal(loc=0, scale=0.33)

        for note in notes:
            # apply swing
            note = self._apply_swing(note)

            if note.is_note:
                # change intonation
                note._pitch += self._intonation[int(note.pitch)] + self._config[
                    "values"
                ]["pitch_deviation_cents"] * 0.01 * np.random.normal(loc=0, scale=0.33)

        # add staccato/legato through pauses
        pauses = []
        for note in notes:
            # legato
            mult = self._current_legato
            new_length = note.duration * mult
            pause = tu.Pause(
                eighth_duration=(note.duration - new_length).eighth_duration,
                time=(note.time + new_length).eighth_duration,
            )
            if pause.duration > 0:
                pauses.append(pause)
                note.duration *= mult

            if note.is_note and note.has_metadata:
                notes.extend(note.metadata)

        notes.extend(pauses)

        # add the other drones
        notes.extend(non_legato_drones)

        ################### convert to midi #########################

        midi_headers = []

        # tempo
        if not self._syncing:
            # add explicit tempo information
            try:
                midi_headers.append(
                    mido.MetaMessage("set_tempo", tempo=self.current_tempo, time=0)
                )
            except Exception as e:
                print(e)
                print(self.current_tempo)

        # add contour information as MIDI CC
        midi_headers.extend(self._contours_to_midi())

        # keyswitches
        midi_headers.extend(self._add_keyswitches())

        # fix notes
        for midi in midi_headers:

            midi.time = notes[0].time.eighth_duration

        return (
            midi_headers,
            notes,
        )

    @property
    def tempo_scale(self):
        return self._eighth_duration_seconds * self._contour_values["tempo_pattern"]

    @property
    def performance_time(self):
        return self._performance_time

    def _add_keyswitches(self):
        notes = []
        # keep track of what is active
        new_keyswitches = []
        # got through articulations
        for articulation in self._config["keyswitches"]:

            articulation_dictionary = self._config["keyswitches"][articulation]

            contour_value = self._contour_values[articulation_dictionary["bind"]]
            kmin = articulation_dictionary["min"]
            kmax = articulation_dictionary["max"]

            # only add new keyswitches
            if contour_value > kmin and contour_value <= kmax:

                new_keyswitches.append(articulation)

                if articulation not in self._last_keyswitches:
                    notes.append(
                        mido.Message(
                            "note_off",
                            velocity=0,
                            time=0,
                            note=articulation_dictionary["key"],
                        )
                    )
                    notes.append(
                        mido.Message(
                            "note_on",
                            velocity=127,
                            time=0,
                            note=articulation_dictionary["key"],
                        )
                    )

            # if updated, change memory
            if len(new_keyswitches) != 0:
                self._last_keyswitches = new_keyswitches

        return notes

    def _contours_to_midi(self):
        messages = []
        values = defaultdict(list)
        for contour_name in self._config["contour_2_control"]:

            contour = contour_name.split("#")[0]
            control = self._config["contour_2_control"][contour_name]["control"]
            value = self._contour_values[contour]

            min_value = self._config["contour_2_control"][contour_name]["min"]
            max_value = self._config["contour_2_control"][contour_name]["max"]
            value = max(0, min(127, round(min_value + value * (max_value - min_value))))

            values[control].append(value)

        for control in values.keys():
            messages.append(
                mido.Message(
                    "control_change",
                    channel=self._config["values"]["midi_channel"],
                    control=control,
                    time=0,
                    value=np.mean(values[control]).astype(int),
                )
            )
        return messages

    def _apply_swing(self, message) -> float:

        x = message.time

        # is it an eight note?
        right_duration = message.duration == 1

        # is it the right place?
        current_location = int(
            (x % (self._tune.time_signature.eighths_per_bar)).eighth_duration
        )
        right_location = current_location in self._config["swing"]["locations"]

        swing = self._current_swing(message.time)

        # make this shorter
        if right_duration and right_location:
            multiplier = 2 / (swing + 1)
        # if next one is shorter, make this longer
        elif (
            right_duration
            and current_location + 1 in self._config["swing"]["locations"]
        ):
            multiplier = 2 * swing / (swing + 1)
        # don't change anything
        else:
            multiplier = 1

        original_duration = message.duration
        new_duration = message.duration * multiplier

        if multiplier < 1:
            message.time = message.time + original_duration - new_duration

        message.duration = new_duration.eighth_duration

        return message

    def _current_notes_per_bar(self, note, drone_name):

        options = self._config["drone"]["drone_sets"][drone_name]["notes_per_bar"]
        amount = self._contours[
            self._config["drone"]["drone_sets"][drone_name]["notes_per_bar_bind"]
        ].at(note.time)
        amount_min = self._config["drone"]["drone_sets"][drone_name]["threshold"]
        if len(options) != 1:
            index = np.round(
                (len(options) - 1) * (amount - amount_min) / (1 - amount_min)
            ).astype(int)
            index = max(0, min(len(options) - 1, index))
            return options[index]
        else:
            return options[0]

    def _add_drone(self, note, drones, drone_name, notes_per_bar):
        """
        Add drones to each note in input.

        :param notes: the notes to add a drone to.
        :param drone: the drone notes to add.

        :return: the input notes, with an added drone.
        """
        if drone_name.startswith("pedal"):
            note_duration = self._tune._score_end_time - self._performance_time
        else:

            note_duration = self._tune.time_signature.eighths_per_bar / notes_per_bar

        notes = []
        delay = 0

        for drone in drones:
            if self._config["drone"]["drone_sets"][drone_name]["transpose"]:
                drone += self._config["values"]["transpose"]

            # delay = random.uniform(0, self._config["drone"]["delay_range"])

            multiplier = self._config["drone"]["drone_sets"][drone_name][
                "velocity_multiplier"
            ]
            velocity = note._velocity

            if multiplier < 0:
                velocity = 127 - velocity
                multiplier = abs(multiplier)

            velocity = min(
                max(
                    self._config["values"]["min_velocity"],
                    min(int(velocity * multiplier), 127),
                ),
                self._config["values"]["max_velocity"],
            )

            notes.append(
                tu.Note(
                    pitch=drone,
                    eighth_duration=(note_duration - delay).eighth_duration,
                    velocity=velocity,
                    time=(note.time + delay).eighth_duration,
                    channel=self._config["drone"]["drone_sets"][drone_name][
                        "midi_channel"
                    ],
                )
            )
            if not drone_name.startswith("pedal"):
                delay += self._config["drone"]["drone_sets"][drone_name]["delay_range"]

        return notes, delay

    def _get_drone(self, reference: int, drone_name) -> np.array:

        drone_threshold = self._config["drone"]["drone_sets"][drone_name]["threshold"]
        drone = np.array([-1]).astype(int)
        drone_perc = self._contour_values[
            self._config["drone"]["drone_sets"][drone_name]["bind"]
        ]
        drone_perc = (drone_perc - drone_threshold) / (1 - drone_threshold)

        # figure out what note is allowed depending on harmony
        harmony = self._tune._current_chord.chord_number

        if not self._config["drone"]["drone_sets"][drone_name]["transpose"]:
            harmony += self._config["values"]["transpose"]

        harmony = int(harmony % 12)
        allowed_harmony = self._tune._current_chord.pitches

        # append root
        if self._config["drone"]["allow_root"]:
            allowed_harmony = np.append(
                allowed_harmony,
                (
                    24
                    + self._tune.key_signature.root
                    + self._config["values"]["transpose"]
                    - harmony
                )
                % 12,
            )

        drone_type = drone_name.split("#")[0]
        # check on what string the note could be played
        available_notes = np.array(
            self._config["drone"]["drone_sets"][drone_name]["notes"]
        )

        index = []

        if drone_type == "bowed":
            distances = reference - available_notes
            distances[distances < 0] = 127
            # string note is being played on
            string = np.argmin(distances)

            # add lower string if there
            if string > 0:
                index.append(string - 1)

            # add upper string if there
            if string < len(available_notes) - 1:
                index.append(string + 1)

            index = np.array(index)

        elif drone_type in ["free", "pedal"]:
            index = np.arange(len(available_notes))

        else:
            raise Exception(f"Unknown drone type {drone_type}.")

        available_notes = available_notes[index]
        available_notes = available_notes[
            np.in1d(
                np.round((12 + available_notes - harmony) % 12),
                allowed_harmony,
            )
        ]

        possible_bases = np.array([*available_notes, reference])
        # old harmony sort
        # index = np.argsort(0.1 * np.arange(len(available_notes)) + (7 * (available_notes - harmony)) % 12)

        # sort based on harmony
        # magic function time

        if self._tune._current_chord.is_user:
            base = self._tune._current_chord.bass + 12 * np.floor(
                min(np.min(self._all_drones), reference) / 12
            )

        else:
            frequencies = lu.midi_to_freq(possible_bases)
            reference_frequency = lu.midi_to_freq(reference)
            reference_to_notes_ratio = reference_frequency / frequencies

            harmony_frequency = lu.midi_to_freq(harmony)
            notes_to_harmony_ratio = frequencies / harmony_frequency

            reference_score = abs(
                reference_to_notes_ratio - np.round(reference_to_notes_ratio)
            )
            harmony_score = abs(
                notes_to_harmony_ratio - np.round(notes_to_harmony_ratio)
            )
            options = 0.75 * harmony_score + 0.25 * reference_score

            if len(options) == 0:
                base = harmony + 12 * np.round(
                    min(np.min(self._all_drones), reference) / 12
                )
                if harmony > 6:
                    base -= 12
            else:
                base = possible_bases[np.argmin(options)]

        frequencies = lu.midi_to_freq(available_notes)
        base_frequency = lu.midi_to_freq(base)
        frequencies_to_base_ratio = frequencies / base_frequency

        score = (
            np.round(
                10
                * abs(frequencies_to_base_ratio - np.round(frequencies_to_base_ratio))
            )
            / 10
        )
        """
        fb_2 = frequencies - base_frequency / 2
        score = (
            -np.nan_to_num(fb_2 / abs(fb_2), nan=1)
            * (1 / frequencies**0.01)
            * abs((2 * (2 * frequencies % base_frequency) / base_frequency) - 1)
        )
        """
        index = np.argsort(score)

        if len(index) != 0:
            # number of strings changes with intensity of signal
            drone_num = np.round(
                self._config["drone"]["drone_sets"][drone_name]["polyphony_min"]
                * (1 - drone_perc)
                + drone_perc
                * self._config["drone"]["drone_sets"][drone_name]["polyphony_max"],
            ).astype(int)

            drone = np.concatenate((drone, available_notes[index[:drone_num]]))

        return drone[1:]

    def get_end_notes(self) -> list[mido.Message]:
        """
        Generate an end note for the tune based on its key.

        :return: the midi messages containing the end note
        """
        # get root and range
        root = int(self._tune._current_chord.root % 12)
        low = min(self._tune.pitches)
        high = max(self._tune.pitches)

        # major or minor
        # chord_pitches = lu.get_chord_pitches(self._contour_values["harmony"])
        chord_pitches = [0]

        # select pitches from tune range
        pitches = np.arange(
            start=low,
            stop=high + 1,
            step=1,
        )

        # get first note of tune
        first_note = self._tune.pitches[0]
        chord_pitches.append((12 + first_note - root) % 12)

        # get last note of tune
        last_note = self._tune.pitches[-1]

        # filter pitches that are too far away
        # reachable within a third
        pitches = pitches[abs(pitches - last_note) < 7]

        # select suitable pitches (e.g. any root, third, fifth within range)
        pitches = pitches[np.in1d((12 + pitches - root) % 12, chord_pitches)]

        if len(pitches) == 0:
            pitches = np.append(pitches, root + (high // 12 + low // 12) / 2)

        # sample weighted by distance
        w = abs(pitches - last_note).astype(float)
        if sum(w) == 0 or len(w) == 1:
            w = np.ones_like(w)
        else:
            w /= sum(w)
            w = 1 - w

        end_pitch = random.choices(pitches, weights=w, k=1)[0]
        end_pitch += self._config["values"]["transpose"]

        # create msgs
        note = tu.Note(
            pitch=end_pitch,
            channel=self._midi_channel,
            time=(self._performance_time + self._tune.durations[-1]).eighth_duration,
            velocity=self._current_velocity,
            eighth_duration=2.0,
        )

        return [note]

    @property
    def do_end_note(self) -> float:
        """
        :return: whether the groover is set up to play end notes.
        """
        return self._config["values"]["do_end_note"]

    @property
    def _current_legato(self):
        return max(
            min(
                1,
                self._config["legato"]["min"]
                + self._legato_amount
                * self._contour_values[self._config["legato"]["bind"]],
            ),
            0,
        )

    def _current_swing(self, time) -> float:
        """
        :return: the current swing amount given the bound countour.
        """
        s1 = self._config["swing"]["min"]
        s2 = self._config["swing"]["max"]
        # perc = self._contour_values[self._config["swing"]["bind"]]
        perc = self._contours[self._config["swing"]["bind"]].at(time)
        return s1 * (1 - perc) + s2 * perc

    @property
    def tempo(self) -> int:
        """
        :return: the user-set tempo.
        """
        base_tempo = self._user_tempo
        with self._tempo_lock:
            if self._external_tempo is not None:
                base_tempo = self._external_tempo

        return base_tempo

    def approach_from_above(self, note_number: int, tune: tu.Tune) -> int:
        """
        Return the midi note number to approach the given note from above.
        If no special approach rule is specified in the configuration file, it will return the next note in the scale of the tune's key from the given note.

        :param note_number: the note to approach.
        :param tune: the reference tune.

        :return: the note used the approach the given note from above.
        """
        note_name = m21.pitch.Pitch(midi=note_number).nameWithOctave
        # use configuration
        if note_name in self._config["approach_from_above"]:
            pitch = m21.pitch.Pitch(self._config["approach_from_above"][note_name])
            return pitch.midi
        # use normal scale
        else:
            index = self._tune.key_signature.semitones_from_root(note_number)
            return lu.above_approach_scale[index] + note_number

    def approach_from_below(self, note_number: int, tune: tu.Tune) -> int:
        """
        Return the midi note number to approach the given note from below.
        If no special approach rule is specified in the configuration file, it will return the previous note in the scale of the tune's key from the given note.

        :param note_number: the note to approach.
        :param tune: the reference tune.

        :return: the note used the approach the given note from below.
        """
        note_name = m21.pitch.Pitch(midi=note_number).nameWithOctave
        # use configuration
        if note_name in self._config["approach_from_below"]:
            pitch = m21.pitch.Pitch(self._config["approach_from_below"][note_name])
            return pitch.midi
        # use normal scale
        else:
            index = self._tune.key_signature.semitones_from_root(note_number)
            return lu.below_approach_scale[index] + note_number

    def generate_ornament(
        self, message: mido.Message, ornament_type: str
    ) -> list[mido.Message]:
        """
        Generate the sequence of notes corresponding to the chosen ornament.

        :param message: the midi message to ornament.
        :param ornament_type: the type of ornament to generate.

        :return: the list of midi events corresponding to the chosen ornament.
        """

        if self._verbose >= 2:
            print(f"\033[38;2;255;0;255m[ORNT]\t{ornament_type}\033[0m")

        ornament_length = self._config["ornamentation"][ornament_type]["length"]
        # sample pitches
        pitches = np.random.normal(
            loc=self._config["ornamentation"][ornament_type]["pitches_mean"],
            scale=self._config["ornamentation"][ornament_type]["pitches_std"],
            size=len(self._config["ornamentation"][ornament_type]["pitches_mean"]),
        )
        # sample velocities
        velocities = np.random.normal(
            loc=self._config["ornamentation"][ornament_type]["velocities_mean"],
            scale=self._config["ornamentation"][ornament_type]["velocities_std"],
            size=len(pitches),
        )

        # sample durations
        durations = np.abs(
            np.random.normal(
                loc=self._config["ornamentation"][ornament_type]["durations_mean"],
                scale=self._config["ornamentation"][ornament_type]["durations_std"],
                size=len(pitches),
            )
        )
        # normalize durations
        durations /= durations.sum()
        durations *= ornament_length

        ornaments = []
        is_slide = self._config["ornamentation"][ornament_type]["slide"]
        offset = message.time
        for i, (p, v, d) in enumerate(zip(pitches, velocities, durations)):

            # if a step and diatonic
            if abs(p) == 1 and self._config["ornamentation"][ornament_type]["diatonic"]:
                if p < 0:
                    new_note = self.approach_from_below(message.pitch, self._tune)
                else:
                    new_note = self.approach_from_above(message.pitch, self._tune)
            else:
                new_note = message.pitch + p

            # if not sliding, quantize
            # slides can be microtonal
            if not is_slide:
                new_note = int(new_note)

            # get note position in scale
            note_index = int(self._tune.key_signature.semitones_from_root(new_note))

            # if quantization needed
            if (
                lu.needs_pitch_quantization[note_index]
                and not is_slide
                and self._config["ornamentation"][ornament_type]["diatonic"]
            ):
                # check both quantizing up and down
                opt = {
                    abs(p - 1): -1,
                    abs(p + 1): 1,
                }
                # if one option leaves the note unchanged, use the other
                if min(opt) == 0:
                    p += opt[max(opt)]
                else:
                    p -= opt[min(opt)]

                new_note = message.pitch + p

            new_pitch = min(127, max(0, new_note))

            # limit velocity in allowed range
            if v != 0:
                vel = min(
                    self._config["values"]["max_velocity"],
                    max(
                        self._config["values"]["min_velocity"],
                        int(self._current_velocity * v),
                    ),
                )
            else:
                vel = 0

            orn_note = tu.Note(
                pitch=new_pitch,
                eighth_duration=d,
                velocity=vel,
                time=offset.eighth_duration,
                slide=is_slide and len(ornaments) == 0,
                channel=self._midi_channel,
            )
            if is_slide and len(ornaments) != 0:
                ornaments[-1].add_slide_target_pitch(orn_note)

            else:
                ornaments.append(orn_note)

            offset += orn_note.duration

        self._eighths_to_skip = -message.duration + ornament_length

        ornaments[-1].duration = message.time + ornament_length - ornaments[-1].time
        if self._eighths_to_skip < 0:
            ornaments[-1].duration += abs(self._eighths_to_skip.eighth_duration)

        if message.has_metadata:
            ornaments.extend(message.metadata)

        return ornaments

    def choose_ornament(self, first_note) -> str:
        """
        Evaluate the ornament specific rules and chooose how the note will be ornamented.


        :return: the chosen ornament type.
        """
        options = []
        options_prob = []

        is_beat = self._is_on_a_beat()
        # create pattern from source notes
        case_len = tu.TimeDelta(eighth_duration=0)
        case_i = 0
        tune_notes = []
        first_pitch = 0
        # iterate until needed
        while case_len < self._max_ornament_length:

            index = min(
                self._note_index + case_i,
                len(self._tune) - 1,
            )
            note = self._tune[index]

            # save first pitch
            if case_i == 0:
                first_pitch = first_note.pitch
                case_len += first_note.duration
                tune_notes.append(first_note)

            elif note.is_note:

                # update length counter
                case_len += note.duration

                # add note
                tune_notes.append(note)

            case_i += 1

        # for each ornament
        for ornament in self._config["ornamentation"]:
            cases = self._config["ornamentation"][ornament]["cases"]

            prob = self._config["ornamentation"][ornament]["probability"]
            if f"orn_{ornament}_prob" in self._contour_values:
                prob = self._contour_values[f"orn_{ornament}_prob"]

            if f"orn_{ornament}" in self._contour_values:

                thr = self._config["ornamentation"][ornament]["threshold"]
                val = self._contour_values[f"orn_{ornament}"]
                if thr < 0:
                    val = 1 - val
                    thr = abs(thr)

                if val <= thr:
                    continue

            if prob == 0:
                continue

            # check elegibility for every listed case
            for c in cases:
                elegible = True
                # on a beat
                if c == "beat":
                    elegible = elegible and is_beat
                elif c == "not beat":
                    elegible = elegible and not is_beat
                else:
                    case_notes = c

                    tune_i = 0
                    for note in case_notes:

                        # target pitch
                        pitch = note[0]

                        # target duration
                        duration = note[1]

                        # actual pitch & duration
                        pitch_difference = tune_notes[tune_i].pitch - first_pitch
                        message_length = tune_notes[tune_i].duration
                        tune_i += 1

                        # check
                        if pitch != "*":
                            elegible = elegible and pitch_difference == pitch

                        elegible = elegible and message_length - duration == 0

                        # if one fails, move on
                        if not elegible:
                            break

                # if found a case, move to next ornament
                if elegible:
                    options.append(ornament)
                    options_prob.append(prob)
                    break
                # else check another case

        prob_sum = sum(options_prob)
        if prob_sum == 0:
            return None
        elif prob_sum < 1:
            options.append(None)
            options_prob.append(1 - prob_sum)
        else:
            options_prob = np.array(options_prob).astype(float)
            options_prob /= options_prob.sum()

        return np.random.choice(options, p=options_prob)

    def can_generate_ornament(self) -> bool:
        """
        :return: whether or not to generate an ornament given the current ornament contour.
        """
        prob = self._contour_values["ornament"]
        return random.choices([True, False], weights=[prob, 1 - prob], k=1)[0]

    def reset(self) -> None:
        """
        Reset all contours so that the next call to `next()` will yield the first value of each contour.
        """
        with self._note_index_lock:
            self._note_index = -1
            for contour_name in self._contours:
                self._contours[contour_name].reset()

    def _is_on_a_beat(self) -> bool:
        """
        Decide if we are on a beat or not, given the current cumulative performance time.

        :return: True if we are on a beat.
        """
        return (
            self._performance_time
            % (
                self._tune.time_signature.eighths_per_bar
                / self._tune.time_signature.beat_count
            )
            == 0
        )

    @property
    def current_tempo(self) -> int:
        """
        :return: the current tempo given the value of the tempo contour. If the option `use_old_tempo_warp` is set to `True` the contour affects tempo in terms of percentage of the original one (e.g. 20% faster); otherwise in terms of a fixed amount of bpms (e.g. 10 bpms faster).
        If an external tempo has been set, the calculated tempo will be interpolated with it according to the user specified percentage.
        """

        calculated_tempo = None
        base_tempo = self.tempo

        bpm = base_tempo.qpm
        value = (
            2
            * self._config["tempo_control"]["tempo_warp_bpms"]
            * (self._contour_values["tempo"] - 0.5)
        )

        calculated_tempo = bpm + value

        if self._config["tempo_control"]["increasing"]:
            self._tempo = min(self._tempo, calculated_tempo)
        else:
            self._tempo = calculated_tempo
        return mido.bpm2tempo(self._tempo)

    @property
    def _eighth_duration_seconds(self) -> float:
        return 30 / mido.tempo2bpm(self.current_tempo)

    def set_transpose(self, value):
        self._config["values"]["transpose"] = value

    def set_droning(self, value):
        self._config["drone"]["active"] = value

    @property
    def _current_velocity(self) -> int:
        """
        :return: the current velocity given the value of the velocity contour.
        """
        max_velocity = self._config["values"]["max_velocity"]
        min_velocity = self._config["values"]["min_velocity"]
        velocity_range = max_velocity - min_velocity
        value = min_velocity + self._contour_values["velocity"] * velocity_range
        if self._is_on_a_beat():
            value += self._config["values"]["beat_velocity_increase"]

        value *= self._contour_values["velocity_pattern"]
        # clamp velocity
        value = max(min(value, max_velocity), min_velocity)
        if np.isnan(value):
            return min_velocity
        return int(value)
