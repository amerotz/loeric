# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.

import argparse
import importlib.resources as ir
import os
import threading
import time
import traceback

import mido

import loeric.groover as gr
import loeric.loeric_utils as lu
import loeric.player as pl
import loeric.tune as tu

# parallel stuff
received_start = threading.Condition()
stop_event = threading.Event()
program_start = 0


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
    global program_start
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "source",
        help="the files to play. If more than one, they will be assigned to each player in order.",
        nargs="+",
        default="",
    )
    parser.add_argument(
        "--config",
        help="the path to a configuration file.",
        type=str,
        default=ir.files("loeric.loeric_config.session").joinpath("session.json"),
    )

    parser.add_argument(
        "-c",
        "--control",
        help="the control change number to monitor to start the session.",
        type=int,
        default=66,
    )
    parser.add_argument(
        "-r",
        "--repeat",
        help="how many times the tune should be repeated",
        type=int,
        default=1,
    )
    parser.add_argument(
        "-qpm",
        help="the tempo of the performance. If None, defaults to the original file's tempo.",
        type=int,
        default=None,
    )

    args = parser.parse_args()
    args = vars(args)

    if len(args["source"]) != 1:

        if args["players"] is not None:
            assert len(args["source"]) == len(args["players"])
        else:
            assert len(args["source"]) == len(args["player_configs"])

    loeric_id = int(time.time())
    if args.get("name") is not None:
        loeric_id = args.get("name")
    scheduler_port = None

    # create Session object
    session = Session(args["config"])

    # set session tempo
    session.set_tempo(args["qpm"])

    single_tune = len(args["source"]) == 1
    if single_tune:
        tune = tu.Tune(
            args["source"][0],
            args["repeat"],
            key=args["force_key"],
            meter=args["force_meter"],
            verbose=1,
            sync_interval=session.sync_interval,
        )

    groovers = []
    players = []
    musicians = args["players"]
    using_configs = False

    if musicians is None:
        musicians = args["player_configs"]
        using_configs = True

    for i, setup in enumerate(musicians):

        # create the part for this musician
        if not single_tune:
            tune = tu.Tune(
                args["source"][i],
                args["repeat"],
                key=args["force_key"],
                meter=args["force_meter"],
                verbose=1,
                sync_interval=session.sync_interval,
            )
        print(f"[SESS] Creating {setup}")

        # players are defined by configuration files
        if using_configs:
            config = setup
            additional_configs = []
        # players are generated using snippets
        else:
            config = None
            additional_configs = [
                lu.general_configs_path / "instrument" / f"{setup}.json",
                lu.general_configs_path / "tune_type" / f"{tune.tune_type}.json",
                lu.general_configs_path / "drone" / "on.json",
                lu.general_configs_path / "control" / "session.json",
                lu.general_configs_path / "ornament" / "variations.json",
            ]

        # create ports
        if args["separate"]:
            outputs.append(
                mido.open_output(f"LOERIC SESSION out #{setup}#", virtual=True)
            )

        groover = gr.Groover(
            tune,
            bpm=args["qpm"],
            config_file=config,
            slow_start=args["slow_start"],
            slow_end=args["slow_end"],
            human_impact=1,
            do_end_note=args["do_end_note"],
            verbose=0,
            midi_channel=2 * i,
            loeric_id=f"{i}_" + os.path.basename(setup)[:7],
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
    for i, g in enumerate(groovers):

        if args["separate"]:
            out = outputs[i]

        # create a player per groover
        p = pl.Player(tempo=g.current_tempo, midi_out=out, midi_out_lock=output_lock)
        players.append(p)

        p.init_playback()

        groover_t = threading.Thread(
            target=play_tune,
            args=(p, g, port, session),
        )
        player_t = threading.Thread(target=player_loop, args=(p, g))
        groover_threads.append(groover_t)
        player_threads.append(player_t)

    # all threads + session loop
    # all_dead = threading.Semaphore(value=total_threads)

    try:
        # set up port and wait
        if scheduler_port is not None:
            print("[SESS] Awaiting message...")

            scheduler_port.callback = get_callback(args["control"])

            with received_start:
                received_start.wait()
        else:
            input("Press any key to start playback:")
            print()

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
        # must_die.set()
        stop_event.set()

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
        stop_event.set()

    # wait for every thread to die
    for groover in groovers:
        groover.stopped.clear()
        groover.playback_resumed.set()

    for player in players:
        player.has_reached_wake_time.set()

    for i, thread in enumerate(groover_threads):
        while thread.is_alive():
            thread.join(1)
        print(f"[SESS] {i+1}/{len(groover_threads)} groover threads dead.")

    for i, thread in enumerate(player_threads):
        while thread.is_alive():
            thread.join(1)
        print(f"[SESS] {i+1}/{len(player_threads)} player threads dead.")

    # close midi input
    if port is not None:
        port.close()
        print("[SESS] Closing midi ports...")
        if port.closed:
            print("[SESS] Closed MIDI input.")

    # make sure to turn off all notes
    if args["separate"]:
        ports = outputs
    else:
        ports = [out]

    for out in ports:
        if out is not None:
            for i in range(127):
                out.send(mido.Message("note_off", velocity=0, note=i, time=0))
            out.reset()
            out.close()
            if out.closed:
                print("[SESS] Closed MIDI output.")


"""
def player_loop_old(player, groover):
    for i, thread in enumerate(player_threads):
        while thread.is_alive():
            thread.join(1)
        print(f"[SESS] {i+1}/{len(player_threads)} player threads dead.")

    # all_dead.acquire()
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
    # all_dead.release()
"""


def player_loop(player, groover):
    try:
        print(f"[PLYR] Started {groover.loeric_id}")
        while not stop_event.is_set():

            # If paused then block indefinitely
            while groover.stopped.is_set() and not stop_event.is_set():
                player.reset()
                groover.playback_resumed.wait()

                # If stop happened while paused then exit
                if stop_event.is_set():
                    break

                player.init_playback()

            # Normal playback
            player.play_next()

    except Exception as e:
        traceback.print_exception(e)
    finally:
        print(f"[PLYR] Terminated {groover.loeric_id}")


def play_tune(player, groover, port, session):

    # set input callback
    if port is not None:

        def callback(message):

            if message.type == "songpos":
                session.handle_human_pos("HUMAN", message.position)
            elif message.is_cc:
                session.handle_human_intensity(
                    "HUMAN", message.control, message.value / 127
                )

        port.callback = callback

    def note_callback(message):
        session.handle_loeric_intensity(groover)

    def songpos_callback(message):
        session.handle_loeric_pos(groover, player, message.position)

    # all_dead.acquire()
    print(f"[GRVR] Started {groover.loeric_id}")
    args = {"verbose": 0}
    lu.play(
        loop_condition=lambda: not stop_event.is_set(),
        groover=groover,
        player=player,
        note_callback=note_callback,
        songpos_callback=songpos_callback,
        repetition_callback=None,
        **args,
    )

    print(f"[GRVR] Terminated {groover.loeric_id}")
    # all_dead.release()
