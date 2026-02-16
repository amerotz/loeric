import argparse
import random
import importlib.resources as ir
import os
import threading
import time
import mido
import json
import numpy as np

from collections import defaultdict


import loeric.tune as tu
import loeric.loeric_utils as lu
import loeric.player as pl
import loeric.groover as gr


"""
from loeric import tune as tu
from loeric import groover as gr
from loeric import player as pl
from loeric import loeric_utils as lu
"""

# parallel stuff
received_start = threading.Condition()
must_die = threading.Event()
all_dead = threading.Semaphore()
program_start = 0


class Session:

    def __init__(self, config, out):

        with open(config, "r") as f:
            self._config = json.load(f)

        # create dictionaries
        self._loeric_positions = {}
        self._was_updated = defaultdict(bool)
        self._loeric_tempos = {}
        self._sleepers = []
        self._sleepers_lock = threading.Lock()
        self._position_lock = threading.Lock()
        self._out = out

        self._intensity_dict = defaultdict(int)
        self._human_impact_dict = defaultdict(int)
        self._action_dict = {}

    @property
    def sync_interval(self):
        return 2 * self._config["tempo_policy"]["sync_interval_quarters"]

    def set_tempo(self, tempo):
        self._last_tempo = tempo
        self._fix_sync_duration = (
            self._config["tempo_policy"]["fix_sync_quarters"] * 60 / self._last_tempo
        )
        self._stop_sync_duration = (
            self._config["tempo_policy"]["stop_sync_quarters"] * 60 / self._last_tempo
        )

        self._songpos_wait = (
            self._config["tempo_policy"]["sync_interval_quarters"]
            * 60
            / self._last_tempo
        )

        self._switch_timer = (
            self._config["attention_policy"]["switch_every_quarters"]
            * 60
            / self._last_tempo
        )

    def session_loop(self):

        all_dead.acquire()
        print("[LOOP] Session loop thread started.")
        while not must_die.is_set():

            # now = time.time()
            # handle sleep/awakening
            with self._sleepers_lock:

                # awake sleeping loerics
                new_sleepers = []
                for s in self._sleepers:

                    # get info
                    groover, start_time, wait_time, sleeper_position = s

                    # if enough time has passed
                    current_time = time.time()
                    if current_time - start_time >= wait_time:
                        # wakey wakey!

                        # unflag stopped
                        with groover.lock:
                            groover.stopped.clear()
                        with self._position_lock:
                            # update  position
                            self._loeric_positions[groover.loeric_id] = (
                                current_time,
                                sleeper_position,
                            )

                        # awake thread
                        groover.playback_resumed.set()

                        print(
                            f"[LOOP] {groover.loeric_id} AWKN at {sleeper_position} ({current_time - program_start})"
                        )
                    else:
                        # nevermind, keep sleeping
                        new_sleepers.append(s)

                self._sleepers = new_sleepers

            # no need to run all the time
            time.sleep(1 / 50)

        all_dead.release()

    def handle_human_pos(self, human_id, position):
        # don't sync the human
        # but record positions
        now = time.time()
        if (
            # if first time
            human_id not in self._loeric_positions
            # or human skipped a beat
            or now - self._loeric_positions[human_id][0] > 2 * self._songpos_wait
        ):
            # get loeric positions
            with self._position_lock:
                positions = [t[1] for t in self._loeric_positions.values()]

            # assume human to be following the fastest loeric
            value = 0
            if len(positions) != 0:
                value = max(positions)

            with self._position_lock:
                self._loeric_positions[human_id] = (now, value)

        # only advance human position
        else:
            with self._position_lock:
                self._loeric_positions[human_id] = (
                    now,
                    self._loeric_positions[human_id][1] + 1,
                )

        """
        print(
            f"[SYNC] {human_id} SENT {self._loeric_positions[human_id][1]} {(self._loeric_positions[human_id][0] - program_start)}"
        )
        """

    def _calculate_position(self, loeric_id):

        with self._position_lock:
            positions = np.array(
                [
                    self._loeric_positions[t][1]
                    for t in self._loeric_positions
                    # if t != loeric_id
                ]
            )
            times = np.array(
                [
                    self._loeric_positions[t][0]
                    for t in self._loeric_positions
                    # if t != loeric_id
                ]
            )

            if len(positions) == 0:
                return self._loeric_positions[loeric_id]

        # agree on which position
        algorithm = self._config["tempo_policy"]["position"]
        if algorithm == "max":
            calculated_position = max(positions)
            timestamp = np.max(times[positions == calculated_position])
        elif algorithm == "min":
            calculated_position = min(positions)
            timestamp = np.min(times[positions == calculated_position])
        elif algorithm == "mode":
            vals, counts = np.unique(
                positions,
                return_counts=True,
            )
            calculated_position = vals[np.argmax(counts)]
            timestamp = np.mean(times[positions == calculated_position])

        return timestamp, calculated_position

    def _put_to_sleep(self, groover, start_time, wait_time, position):
        with self._sleepers_lock:
            self._sleepers.append(
                # in (songpos wait - diff) the reference will be at p+1
                # (now, later, groover, position)
                (groover, start_time, wait_time, position)
            )

    def _hard_fix(self, groover, position):
        with groover.lock:
            # tell groover to wait
            groover.stopped.set()

            for i in range(127):
                self._out.send(
                    mido.Message(
                        "note_off", time=0, channel=groover._midi_channel, note=i
                    )
                )
                self._out.send(
                    mido.Message(
                        "note_off", time=0, channel=groover._drone_midi_channel, note=i
                    )
                )

            # tell groover to start at next songpos
            groover.jump_to_pos(int(position))

    def _calculate_new_tempo(self, now, expected_timestamp):
        Q = self._config["tempo_policy"]["sync_interval_quarters"]
        v1 = self._last_tempo
        v0 = self._last_tempo
        t0 = now
        t1 = expected_timestamp
        f1t1 = v1 * t1
        q1 = (f1t1 + Q) / v1
        f1q1 = v1 * q1
        f0t0 = v0 * t0
        w = (f1q1 - f0t0) / (q1 - t0)

        return w

    def handle_loeric_pos(self, groover: gr.Groover, position: int):
        # obtain timestamp
        now = time.time()

        # who sent this?
        loeric_id = groover.loeric_id

        with self._position_lock:
            # store a tuple (time, position) for each
            self._loeric_positions[loeric_id] = (now, position)

        # obtain sync position
        timestamp, calculated_position = self._calculate_position(loeric_id)

        # print(f"[SYNC] {loeric_id} SENT {position} ({now-program_start})")

        # expected timestamp
        expected_songpos_timestamp = (
            timestamp + (position - calculated_position) * self._songpos_wait
        )

        # calculate difference in timestamp
        diff = abs(now - expected_songpos_timestamp)
        fix_thr = self._fix_sync_duration
        stop_thr = self._stop_sync_duration

        # if tempo was updated before
        # we need to reset it to the original
        if self._was_updated[loeric_id]:
            with groover.lock:
                groover.set_tempo(self._last_tempo)
            self._was_updated[loeric_id] = False

        # hard fix
        # stop and continue from next beat
        if diff > stop_thr:

            # add it to the sleepers queue
            # to be awaken at next position
            wake_position = calculated_position + 1
            if position > calculated_position:
                wake_position = position

            # tell groover to start at next songpos
            self._hard_fix(groover, wake_position)

            self._put_to_sleep(
                groover=groover,
                start_time=now,
                wait_time=self._songpos_wait - (now - timestamp),
                position=wake_position,
            )

            print(
                f"[SYNC] {loeric_id} SLEP at {calculated_position}",
                self._songpos_wait + timestamp - program_start,
            )

            with self._position_lock:
                self._loeric_positions[loeric_id] = (
                    expected_songpos_timestamp,
                    position,
                )

        # soft fix
        # send a tempo bump
        elif diff >= fix_thr:

            # calculate the new tempo
            # so that we synchronize on the next beat
            new_tempo = self._calculate_new_tempo(now, expected_songpos_timestamp)
            if new_tempo > 200:
                print(new_tempo, calculated_position, position)

            with groover.lock:
                groover.set_tempo(new_tempo)
            self._was_updated[loeric_id] = True

            with self._position_lock:
                self._loeric_positions[loeric_id] = (
                    expected_songpos_timestamp,
                    position,
                )

    def handle_human_intensity(self, human_id, intensity, human_impact):

        # keep track of intensity
        self._intensity_dict[human_id] = intensity

        # keep track of human_impact
        self._human_impact_dict[human_id] = human_impact

    def handle_loeric_intensity(self, groover: gr.Groover):

        now = time.time()

        # who sent this?
        loeric_id = groover.loeric_id

        # keep track of intensity
        self._intensity_dict[loeric_id] = np.mean(
            groover.get_control_value(self._config["intensity_control_out"])
        )

        # keep track of human_impact
        self._human_impact_dict[loeric_id] = np.mean(
            groover.get_control_value(self._config["human_impact_control_out"])
        )

        if loeric_id not in self._action_dict:
            self._action_dict[loeric_id] = (
                now - random.random() * self._switch_timer,
                random.choice(
                    list(self._config["attention_policy"]["behaviors"].keys())
                ),
                loeric_id,
            )

        diff = now - self._action_dict[loeric_id][0]
        # choose new action
        if diff >= self._switch_timer:

            players = [p for p in self._intensity_dict.keys() if str(p) != loeric_id]
            # backoff or
            # match
            # any group of players
            # action = random.choice(["backoff", "match", "lead"])
            action = random.choice(
                list(self._config["attention_policy"]["behaviors"].keys())
            )
            n = 1
            if len(players) < 1:
                return
            elif len(players) > 1:
                n = random.randint(
                    min(
                        self._config["attention_policy"]["attention_group_min_size"],
                        len(players),
                    ),
                    min(
                        self._config["attention_policy"]["attention_group_max_size"],
                        len(players),
                    ),
                )
            group = random.sample(players, n)

            self._action_dict[loeric_id] = (now, action, group)
            print(f"[SESS]\t{loeric_id:10}\t{action}\t{group}")

        _, action, group = self._action_dict[loeric_id]
        if type(group) is not list:
            group = [group]

        # intensity
        int_value = 0
        algorithm = self._config["attention_policy"]["behaviors"][action][
            "intensity_aggregator"
        ]
        if algorithm == "mean":
            int_value = np.mean([self._intensity_dict[p] for p in group])
        elif algorithm == "min":
            int_value = np.min([self._intensity_dict[p] for p in group])
        elif algorithm == "max":
            int_value = np.max([self._intensity_dict[p] for p in group])
        elif algorithm == "constant":
            pass

        int_value *= self._config["attention_policy"]["behaviors"][action][
            "intensity_multiplier"
        ]
        int_value += self._config["attention_policy"]["behaviors"][action][
            "intensity_constant"
        ]

        hi_value = 0
        algorithm = self._config["attention_policy"]["behaviors"][action][
            "human_impact_aggregator"
        ]
        if algorithm == "mean":
            hi_value = np.mean([self._human_impact_dict[p] for p in group])
        elif algorithm == "min":
            hi_value = np.min([self._human_impact_dict[p] for p in group])
        elif algorithm == "max":
            hi_value = np.max([self._human_impact_dict[p] for p in group])
        elif algorithm == "constant":
            pass

        hi_value *= self._config["attention_policy"]["behaviors"][action][
            "human_impact_multiplier"
        ]
        hi_value += self._config["attention_policy"]["behaviors"][action][
            "human_impact_constant"
        ]

        int_value = min(int_value, 1)
        int_value = max(int_value, 0)

        hi_value = min(hi_value, 1)
        hi_value = max(hi_value, 0)

        groover.set_control_value(self._config["intensity_control_in"], int_value)

        groover.set_control_value(self._config["human_impact_control_in"], hi_value)


def get_callback(control):

    def check_skips(msg):

        if msg.type == "control_change" and msg.control != control:
            return
        if msg.value == 127:
            return

        if check_skips.counter == 0:
            with received_start:
                received_start.notify()
            print("Received start")
            check_skips.counter += 1

    check_skips.counter = 0

    return check_skips


def main():
    global all_dead, program_start
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    player_args = parser.add_mutually_exclusive_group()
    player_args.add_argument(
        "--player_configs",
        help="the configuration files for each player.",
        nargs="+",
        type=str,
        default=None,
    )
    player_args.add_argument(
        "--players",
        help="the instruments for each player.",
        nargs="+",
        type=str,
        default=None,
    )
    parser.add_argument("--ireland", action="store_true")
    parser.add_argument(
        "--name",
        type=str,
    )

    dir_path = os.path.dirname(os.path.realpath(__file__))
    parser.add_argument(
        "--config",
        help="the path to a configuration file. Every option included in the configuration file will override command line arguments.",
        type=str,
        default=ir.files("loeric.loeric_config.session").joinpath("session.json"),
    )
    input_args = parser.add_mutually_exclusive_group()
    input_args.add_argument(
        "--create-in",
        help="whether to create a new MIDI input port or not",
        action="store_true",
    )
    input_args.add_argument(
        "-i",
        "--input",
        help="the input MIDI port for the performance.",
        type=int,
        default=None,
    )

    output_args = parser.add_mutually_exclusive_group()
    output_args.add_argument(
        "--create-out",
        help="whether to create a new MIDI output port or not",
        action="store_true",
    )
    output_args.add_argument(
        "-o",
        "--output",
        help="the output MIDI port for the performance.",
        type=int,
        default=None,
    )

    sync_args = parser.add_mutually_exclusive_group()
    sync_args.add_argument(
        "--create-sync",
        help="whether to create a new MIDI sync port or not",
        action="store_true",
    )
    sync_args.add_argument(
        "-s",
        "--sync",
        help="the sync MIDI port for the performance.",
        type=int,
        default=None,
    )
    parser.add_argument(
        "-c",
        "--control",
        help="the control change number to monitor to start the session.",
        type=int,
        default=66,
    )
    parser.add_argument(
        "--do-end-note",
        help="plays a final note at the end of all repetitions",
        action="store_true",
    )
    parser.add_argument(
        "--slow-start",
        help="starts the performance at a slower tempo and gradually increases it.",
        action="store_true",
    )
    parser.add_argument(
        "--slow-end",
        help="ends the performance at a slower tempo.",
        action="store_true",
    )
    parser.add_argument(
        "--force-key",
        help="overrides any key information in the tune.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--force-meter",
        help="overrides any time signature information in the tune.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "-r",
        "--repeat",
        help="how many times the tune should be repeated",
        type=int,
        default=1,
    )
    parser.add_argument(
        "-bpm",
        help="the tempo of the performance. If None, defaults to the original file's tempo.",
        type=int,
        default=None,
    )

    args = parser.parse_args()
    args = vars(args)

    loeric_id = int(time.time())
    if args.get("name") is not None:
        loeric_id = args.get("name")
    scheduler_port = None

    if args["create_in"]:
        port = mido.open_input(f"LOERIC SESSION in #{loeric_id}#", virtual=True)

    if args["create_out"]:
        out = mido.open_output(f"LOERIC SESSION out #{loeric_id}#", virtual=True)

    if args["create_sync"]:
        scheduler_port = mido.open_input(
            f"LOERIC SESSION sync #{loeric_id}#", virtual=True
        )

    input_defined = args["input"] is not None or args["create_in"]
    output_defined = args["output"] is not None or args["create_out"]

    saving_defined = False

    inport, outport = lu.get_ports(
        input_number=args["input"],
        output_number=args["output"],
        list_ports=False,
        create_in=args["create_in"],
        create_out=args["create_out"],
        prompt_in=(not input_defined) and (not output_defined) and (not saving_defined),
        prompt_out=(not output_defined) and (input_defined or not saving_defined),
    )

    # open in
    if args["create_in"]:
        pass
    elif inport is not None:
        port = mido.open_input(inport)
    else:
        port = None

    # open out
    if args["create_out"]:
        pass
    elif outport is None:
        out = None
    else:
        out = mido.open_output(outport)

    # open sync
    if args["create_sync"]:
        pass
    elif args["sync"] is not None:
        scheduler_port = mido.open_input(mido.get_input_names()[args["sync"]])

    # create Session object
    session = Session(args["config"], out)

    # set session tempo
    session.set_tempo(args["bpm"])

    tune = tu.Tune(
        args["source"],
        args["repeat"],
        key=args["force_key"],
        meter=args["force_meter"],
        verbose=1,
        sync_interval=session.sync_interval,
    )

    groovers = []
    players = args["players"]
    using_configs = False

    if players is None:
        players = args["player_configs"]
        using_configs = True

    for i, setup in enumerate(players):

        print(f"[SESS] Creating {setup}")
        if using_configs:
            config = setup
            additional_configs = []
        else:
            config = None
            additional_configs = [
                lu.general_configs_path / "instrument" / f"{setup}.json",
                lu.general_configs_path / "tune_type" / f"{tune.tune_type}.json",
                lu.general_configs_path / "drone" / "on.json",
                lu.general_configs_path / "control" / "session.json",
                lu.general_configs_path / "ornament" / "variations.json",
            ]
            if args.get("ireland"):
                additional_configs.append(
                    lu.general_configs_path / "synth" / "kontakt_ireland.json"
                )
                additional_configs.append(
                    lu.general_configs_path / "control" / "velocity_to_modulation.json"
                )

        groover = gr.Groover(
            tune,
            bpm=args["bpm"],
            config_file=config,
            slow_start=args["slow_start"],
            slow_end=args["slow_end"],
            human_impact=1,
            do_end_note=args["do_end_note"],
            verbose=0,
            midi_channel=2 * i,
            loeric_id=setup.split(".json")[0],
            syncing=True,
            seed=int(time.time()),
            additional_configs=additional_configs,
        )

        groovers.append(groover)

    groover_threads = []
    player_threads = []
    # create session loop
    session_t = threading.Thread(target=session.session_loop, args=())

    # create players
    for g in groovers:
        # create a player per groover
        p = pl.Player(tempo=g.current_tempo, midi_out=out)
        p.init_playback()

        groover_t = threading.Thread(
            target=play_tune,
            args=(p, tune, g, port, session),
        )
        player_t = threading.Thread(target=player_loop, args=(p, g))
        groover_threads.append(groover_t)
        player_threads.append(player_t)

    # all threads + session loop
    total_threads = 2 * len(groover_threads) + 1
    all_dead = threading.Semaphore(value=total_threads)

    try:
        # set up port and wait
        if scheduler_port is not None:
            print("[SESS] Awaiting message...")

            scheduler_port.callback = get_callback(args["control"])

            with received_start:
                received_start.wait()

        program_start = time.time()
        # start session
        session_t.start()

        # start all threads
        for thread in groover_threads:
            thread.start()

        for thread in player_threads:
            thread.start()

        ##################################################

        """
        import matplotlib.pyplot as plt
        from matplotlib.animation import FuncAnimation
        from collections import deque

        WINDOW = 20  # sliding window size

        # Create a deque for each key
        buffers = {g.loeric_id: deque(maxlen=WINDOW) for g in groovers}

        # Colors for each line (optional)
        colors = ["r", "g", "b", "m", "c", "y", "k"]

        # --- Plot setup ---
        fig, ax = plt.subplots()

        lines = {}
        for i, k in enumerate(session._intensity_dict.keys()):
            (line,) = ax.plot([], [], label=k, color=colors[i % len(colors)])
            lines[k] = line

        ax.legend(loc="upper left")
        ax.set_title("Live Multi-Line Sliding Window")
        ax.set_xlim(0, WINDOW - 1)

        def animate(frame):

            # Append new value to each buffer
            for k in session._intensity_dict.keys():
                buffers[k].append(session._intensity_dict[k])
                x = range(len(buffers[k]))
                y = list(buffers[k])
                lines[k].set_data(x, y)

            # Adjust y-limits based on current values
            all_vals = [v for buf in buffers.values() for v in buf]
            if all_vals:
                ax.set_ylim(min(all_vals) - 0.1, max(all_vals) + 0.1)

            return lines.values()

        anim = FuncAnimation(fig, animate, interval=200, blit=False)  # update rate (ms)
        plt.show()
        anim.copy()

        ##################################################
        """
        # join all groover threads
        for thread in groover_threads:
            while thread.is_alive():
                thread.join(1)

        # now kill the others
        must_die.set()

        # join player threads to kill them
        for thread in player_threads:
            while thread.is_alive():
                thread.join(1)

        # join session thread to kill it
        while session_t.is_alive():
            session_t.join(1)

    except KeyboardInterrupt:
        print("[SESS] Playback stopped by user.")
        # tell threads to stop
        must_die.set()

    # wait for every thread to die
    for i in range(total_threads):
        all_dead.acquire()
        print(f"[SESS] {i+1}/{total_threads} threads dead.")

    # close midi input
    if port is not None:
        port.close()
        print("[SESS] Closing midi ports...")
        if port.closed:
            print("[SESS] Closed MIDI input.")

    # make sure to turn off all notes
    if out is not None:
        for i in range(127):
            out.send(mido.Message("note_off", velocity=0, note=i, time=0))
        out.reset()
        out.close()
        if out.closed:
            print("[SESS] Closed MIDI output.")


def player_loop(player, groover):

    all_dead.acquire()
    print(f"[PLYR] Started {groover.loeric_id}")
    while not must_die.is_set():

        while groover.stopped.is_set():
            player.reset()
            print("player waiting play")
            groover.playback_resumed.wait()
            print("player awake")
            player.init_playback()

        player.play_next()

    print(f"[PLYR] Terminated {groover.loeric_id}")
    all_dead.release()


def play_tune(player, tunes, groover, port, session):

    # set input callback
    if port is not None:
        port.callback = groover.check_midi_control()

    def loop_condition():
        return not must_die.is_set()

    def note_callback(message):
        session.handle_loeric_intensity(groover)

    def songpos_callback(message):
        session.handle_loeric_pos(groover, message.position)

    all_dead.acquire()
    print(f"[GRVR] Started {groover.loeric_id}")
    args = {"verbose": True}
    lu.play(
        groover,
        player,
        loop_condition=loop_condition,
        note_callback=note_callback,
        songpos_callback=songpos_callback,
        repetition_callback=None,
        **args,
    )

    print(f"[GRVR] Terminated {groover.loeric_id}")
    all_dead.release()
