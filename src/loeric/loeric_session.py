import argparse
import os
import threading
import time
import mido
import json
import numpy as np

from collections import defaultdict

"""
from . import tune as tu
from . import groover as gr
from . import player as pl
from . import loeric_utils as lu
"""
from loeric import tune as tu
from loeric import groover as gr
from loeric import player as pl
from loeric import loeric_utils as lu

# parallel stuff
received_start = threading.Condition()
must_die = threading.Event()


class Session:

    def __init__(self, config):

        with open(config, "r") as f:
            self._config = json.load(f)

        # create dictionaries
        self._loeric_positions = {}
        self._was_updated = defaultdict(bool)
        self._loeric_tempos = {}
        self._sleepers = []
        self._sleepers_lock = threading.Lock()
        self._position_lock = threading.Lock()

    @property
    def sync_interval(self):
        return self._config["tempo_policy"]["sync_interval_quarters"]

    def set_tempo(self, tempo):
        self._last_tempo = tempo
        self._fix_sync_duration = (
            self._config["tempo_policy"]["fix_sync_quarters"] * 60 / self._last_tempo
        )
        self._stop_sync_duration = (
            self._config["tempo_policy"]["stop_sync_quarters"] * 60 / self._last_tempo
        )
        """
        self._syncing_wait = (
            self._config["tempo_policy"]["sync_every_n_intervals"]
            * self._config["tempo_policy"]["sync_interval_quarters"]
            * 60
            / self._last_tempo
        )
        """

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

        global all_dead

        all_dead.acquire()
        print("[LOOP] Session loop thread started.")
        while not must_die.is_set():

            now = time.time()
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
                        with groover.lock:
                            # unflag stopped
                            groover.stopped.clear()
                        """
                        with self._position_lock:
                            # update  position
                            self._loeric_positions[groover.loeric_id] = (
                                current_time,
                                sleeper_position,
                            )
                        """

                        # awake thread
                        with groover.playback_resumed:
                            groover.playback_resumed.notify_all()

                            print(
                                f"[LOOP] {groover.loeric_id} AWKN at {sleeper_position}"
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
            not human_id in self._loeric_positions
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

        print(
            f"[SYNC] {human_id} SENT {self._loeric_positions[human_id][1] (self._loeric_positions[human_id][0])}"
        )

    def _calculate_position(self):

        with self._position_lock:
            # agree on which position
            algorithm = self._config["tempo_policy"]["position"]
            if algorithm == "max":
                calculated_position = max(
                    [t[1] for t in self._loeric_positions.values()]
                )
            elif algorithm == "min":
                calculated_position = min(
                    [t[1] for t in self._loeric_positions.values()]
                )
            elif algorithm == "mode":
                vals, counts = np.unique(
                    [t[1] for t in self._loeric_positions.values()],
                    return_counts=True,
                )
                calculated_position = vals[np.argmax(counts)]
            # agree on what time
            timestamp = np.mean(
                [
                    t[0]
                    for t in self._loeric_positions.values()
                    if t[1] == calculated_position
                ]
            )

        return calculated_position, timestamp

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

            # tell groover to start at next songpos
            groover.jump_to_pos(position)

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
        calculated_position, timestamp = self._calculate_position()

        # print(f"[SYNC] {loeric_id} SENT {position} ({now})")

        # expected timestamp
        """
        expected_syncing_timestamp = (
            timestamp - (calculated_position - position) * self._syncing_wait
        )
        """
        expected_songpos_timestamp = (
            timestamp - (calculated_position - position) * self._songpos_wait
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

            # tell groover to start at next songpos
            self._hard_fix(groover, calculated_position + 1)

            # add it to the sleepers queue
            # to be awaken at next position
            current_time = time.time()
            self._put_to_sleep(
                groover=groover,
                start_time=current_time,
                wait_time=self._songpos_wait - (current_time - timestamp),
                position=calculated_position + 1,
            )

            print(f"[SYNC] {loeric_id} SLEP at {calculated_position}")

        # soft fix
        # send a tempo bump
        elif diff >= fix_thr:

            # calculate the new tempo
            # so that we synchronize on the next beat
            new_tempo = self._calculate_new_tempo(now, expected_songpos_timestamp)
            print(new_tempo)

            with groover.lock:
                groover.set_tempo(new_tempo)
            self._was_updated[loeric_id] = True

    def sync_intensity(self, inports, outports):
        global must_die, all_dead
        all_dead.acquire()

        int_dict = defaultdict(int)
        hi_dict = defaultdict(int)
        action_dict = {}

        while not must_die.is_set():
            # receive message and port
            bundle = list(
                mido.ports.multi_receive(inports, yield_ports=True, block=False)
            )
            now = time.time()
            if len(bundle) == 0:
                continue
            port, msg = bundle[0]
            if msg.type != "control_change" or (
                msg.control != self._config["human_impact_control_in"]
                and msg.control != self._config["intensity_control_in"]
            ):
                continue

            # who sent this?
            loeric_id = re.search("#.*#", port.name)[0]

            now = time.time()
            # keep track of intensity
            if msg.control == self._config["intensity_control_in"]:
                int_dict[loeric_id] = msg.value / 127

            # keep track of human_impact
            elif msg.control == self._config["human_impact_control_in"]:
                hi_dict[loeric_id] = msg.value / 127

            # don't consider human for actions
            if "HUMAN" in port.name:
                continue

            if loeric_id not in action_dict:
                action_dict[loeric_id] = (
                    now - random.random() * self._switch_timer,
                    random.choice(
                        list(self._config["attention_policy"]["behaviors"].keys())
                    ),
                    loeric_id,
                )
                print("added")

            diff = now - action_dict[loeric_id][0]
            # choose new action
            if diff >= self._switch_timer:

                players = [p for p in int_dict.keys() if str(p) != loeric_id]
                # backoff or
                # match
                # any group of players
                # action = random.choice(["backoff", "match", "lead"])
                action = random.choice(
                    list(self._config["attention_policy"]["behaviors"].keys())
                )
                n = 1
                if len(players) < 1:
                    continue
                elif len(players) > 1:
                    n = random.randint(
                        min(
                            self._config["attention_policy"][
                                "attention_group_min_size"
                            ],
                            len(players),
                        ),
                        min(
                            self._config["attention_policy"][
                                "attention_group_max_size"
                            ],
                            len(players),
                        ),
                    )
                group = random.sample(players, n)

                action_dict[loeric_id] = (now, action, group)
                print(loeric_id, action, group)

            # output port
            out_port = None
            for p in outports:
                if loeric_id == re.search("#.*#", p.name)[0]:
                    out_port = p
                    break

            _, action, group = action_dict[loeric_id]
            if type(group) is not list:
                group = [group]

            # intensity
            int_value = 0
            algorithm = self._config["attention_policy"]["behaviors"][action][
                "intensity_aggregator"
            ]
            if algorithm == "mean":
                int_value = np.mean([int_dict[p] for p in group])
            elif algorithm == "min":
                int_value = np.min([int_dict[p] for p in group])
            elif algorithm == "max":
                int_value = np.max([int_dict[p] for p in group])
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
                hi_value = np.mean([hi_dict[p] for p in group])
            elif algorithm == "min":
                hi_value = np.min([hi_dict[p] for p in group])
            elif algorithm == "max":
                hi_value = np.max([hi_dict[p] for p in group])
            elif algorithm == "constant":
                pass

            hi_value *= self._config["attention_policy"]["behaviors"][action][
                "human_impact_multiplier"
            ]
            hi_value += self._config["attention_policy"]["behaviors"][action][
                "human_impact_constant"
            ]

            int_value *= 127
            int_value = int(int_value)
            int_value = min(int_value, 127)
            int_value = max(int_value, 0)

            hi_value *= 127
            hi_value = int(hi_value)
            hi_value = min(hi_value, 127)
            hi_value = max(hi_value, 0)

            # prepare message
            if out_port is not None:
                msg = mido.Message(
                    "control_change",
                    value=int_value,
                    control=self._config["intensity_control_out"],
                )
                out_port.send(msg)
                msg = mido.Message(
                    "control_change",
                    value=hi_value,
                    control=self._config["human_impact_control_out"],
                )
                out_port.send(msg)

        all_dead.release()


def get_callback(control):

    def check_skips(msg):
        global received_start

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
    global all_dead
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "--players",
        help="the self._configuration files for each player.",
        nargs="+",
        type=str,
        default=None,
    )
    dir_path = os.path.dirname(os.path.realpath(__file__))
    parser.add_argument(
        "--config",
        help="the path to a configuration file. Every option included in the configuration file will override command line arguments.",
        type=str,
        default=f"{dir_path}/loeric_config/session/session.json",
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
    session = Session(args["config"])

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
    for i, config in enumerate(args["players"]):

        print(f"[SESSION] Creating {config}")
        groover = gr.Groover(
            tune,
            bpm=args["bpm"],
            config_file=config,
            slow_start=args["slow_start"],
            slow_end=args["slow_end"],
            human_impact=1,
            do_end_note=args["do_end_note"],
            verbose=0,
            # to account for drones
            midi_channel=2 * i,
            loeric_id=config.split(".json")[0],
            syncing=True,
        )

        groovers.append(groover)

    threads = []
    # create session loop
    session_t = threading.Thread(target=session.session_loop, args=())

    # create players
    for g in groovers:
        player = pl.Player(tempo=g.current_tempo, midi_out=out)
        player.init_playback()

        player_t = threading.Thread(
            target=play_tune,
            args=(player, tune, g, port, session),
        )
        threads.append(player_t)

    # all threads + session loop
    all_dead = threading.Semaphore(value=len(threads) + 1)

    print("[SESSION] Awaiting message...")
    try:
        # set up port and wait
        if scheduler_port is not None:

            scheduler_port.callback = get_callback(args["control"])

            with received_start:
                received_start.wait()

        # start session
        session_t.start()

        # start all threads
        for player_t in threads:
            player_t.start()

        # join all threads
        for player_t in threads:
            while player_t.is_alive():
                player_t.join(1)

        must_die.set()
        # join session thread to kill it
        while session_t.is_alive():
            session_t.join(1)

    except KeyboardInterrupt:
        print("[SESSION] Playback stopped by user.")
        # tell threads to stop
        must_die.set()

    # wait for every thread to die
    for i, t in enumerate(threads):
        all_dead.acquire()
        print(f"[SESSION] {i+1}/{len(threads)} threads dead.")

    # close midi input
    if port is not None:
        port.close()
        print("[SESSION] Closing midi ports...")
        if port.closed:
            print("[SESSION] Closed MIDI input.")

    # make sure to turn off all notes
    if out is not None:
        for i in range(127):
            out.send(mido.Message("note_off", velocity=0, note=i, time=0))
        out.reset()
        out.close()
        if out.closed:
            print("[SESSION] Closed MIDI output.")


def play_tune(player, tunes, groover, port, session):
    global must_die, all_dead

    all_dead.acquire()
    print(f"[GRVR] Started {groover.loeric_id}")

    # set input callback
    if port is not None:
        port.callback = groover.check_midi_control()

    # iterate over messages
    while not must_die.is_set():

        if groover.stopped.is_set():
            player.reset()
            with groover.playback_resumed:
                groover.playback_resumed.wait()
            player.init_playback()

        message = groover.next_event()
        if message is None:
            break

        if message.type == "sysex":
            # print(f"Repetition {message.data[0]+1}")
            groover._offset = 0
            groover._swing_offset = 0

            continue

        # perform notes
        elif lu.is_note(message):
            # make the groover play the messages
            new_messages = groover.perform(message)
        # keep meta messages intact
        else:
            if message.type == "songpos":
                session.handle_loeric_pos(groover, message.pos)
            new_messages = groover.perform(message)
        # play
        player.play(new_messages)

    # play an end note
    if groover.do_end_note:
        groover.reset_contours()
        groover.advance_contours()
        player.play(groover.get_end_notes())

    print(f"[GRVR] Terminated {groover.loeric_id}")
    all_dead.release()


main()
