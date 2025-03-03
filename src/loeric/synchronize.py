import mido
import os
import pandas as pd
import numpy as np
import re
import math
import threading
import random
import time
import traceback
import json
import argparse
from collections import defaultdict


songpos_wait = 0
last_tempo = 0
switch_timer = 0
fix_sync_duration = 0
stop_sync_duration = 0

# parallel stuff
exiting = threading.Event()
port_lock = threading.Lock()
all_dead = threading.Semaphore(value=2)


def send_tempo(tempo, port):
    tup = [69]
    while tempo > 0:
        v = min(tempo, 127)
        tup.append(v)
        tempo -= v
    msg = mido.Message("sysex", data=tuple(tup))
    port.send(msg)


def update_tempo(tempo):
    global songpos_wait, last_tempo, switch_timer, fix_sync_duration, stop_sync_duration, config
    last_tempo = tempo
    fix_sync_duration = config["tempo_policy"]["fix_sync_multiplier"] * 60 / last_tempo
    stop_sync_duration = (
        config["tempo_policy"]["stop_sync_multiplier"] * 60 / last_tempo
    )
    songpos_wait = config["sync_interval"] * 60 / last_tempo
    switch_timer = config["switch_every"] * songpos_wait


def sync_intensity(inports, outports):
    global songpos_wait, last_tempo, switch_timer, fix_sync_duration, stop_sync_duration, exiting, all_dead, config
    all_dead.acquire()
    shell_print("Intensity Sync ON.")
    int_dict = defaultdict(int)
    hi_dict = defaultdict(int)
    action_dict = {}
    df_action = pd.DataFrame(columns=["TIME", "ID", "ACTION", "GROUP"])
    df_values = pd.DataFrame(columns=["TIME", "ID", "TYPE", "VALUE", "PARAM"])
    while not exiting.is_set():
        try:
            # receive message and port
            bundle = list(
                mido.ports.multi_receive(inports, yield_ports=True, block=False)
            )
            now = time.time()
            if len(bundle) == 0:
                continue
            port, msg = bundle[0]
            if msg.type != "control_change" or (
                msg.control != config["human_impact_control_in"]
                and msg.control != config["intensity_control_in"]
            ):
                continue

            # who sent this?
            loeric_id = re.search("#.*#", port.name)[0]

            now = time.time()
            # keep track of intensity
            if msg.control == config["intensity_control_in"]:
                int_dict[loeric_id] = msg.value / 127

                df_values.loc[len(df_values)] = [
                    now,
                    loeric_id,
                    "receive",
                    msg.value,
                    "intensity",
                ]
            # keep track of human_impact
            elif msg.control == config["human_impact_control_in"]:
                hi_dict[loeric_id] = msg.value / 127

                df_values.loc[len(df_values)] = [
                    now,
                    loeric_id,
                    "receive",
                    msg.value,
                    "human_impact",
                ]

            # don't consider human for actions
            if "HUMAN" in port.name:
                continue

            if loeric_id not in action_dict:
                action_dict[loeric_id] = (
                    now - random.random() * switch_timer,
                    "match",
                    loeric_id,
                )
                #print("added")

            diff = now - action_dict[loeric_id][0]
            # choose new action
            if diff >= switch_timer:

                players = [p for p in int_dict.keys() if str(p) != loeric_id]
                # backoff or
                # match
                # any group of players
                # action = random.choice(["backoff", "match", "lead"])
                action = random.choice(
                    list(config["attention_policy"]["behaviors"].keys())
                )
                n = 1
                if len(players) < 1:
                    continue
                elif len(players) > 1:
                    n = random.randint(
                        min(
                            config["attention_policy"]["attention_group_min_size"],
                            len(players),
                        ),
                        min(
                            config["attention_policy"]["attention_group_max_size"],
                            len(players),
                        ),
                    )
                group = random.sample(players, n)

                action_dict[loeric_id] = (now, action, group)
                #print(loeric_id, action, group)
                df_action.loc[len(df_action)] = [now, loeric_id, action, group]

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
            algorithm = config["attention_policy"]["behaviors"][action][
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

            int_value *= config["attention_policy"]["behaviors"][action][
                "intensity_multiplier"
            ]
            int_value += config["attention_policy"]["behaviors"][action][
                "intensity_constant"
            ]

            hi_value = 0
            algorithm = config["attention_policy"]["behaviors"][action][
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

            hi_value *= config["attention_policy"]["behaviors"][action][
                "human_impact_multiplier"
            ]
            hi_value += config["attention_policy"]["behaviors"][action][
                "human_impact_constant"
            ]
            """
            # send intensity signal according to action
            int_value = np.mean([int_dict[p] for p in group])
            hi_value = 0.5
            if action == "backoff":
                int_value = np.min([int_dict[p] for p in group])
                hi_value = 0
                int_value *= 0.5
            elif action == "lead":
                int_value = np.max([int_dict[p] for p in group])
                int_value *= 1.5
                hi_value = 1
            elif action == "match":
                pass
            """

            int_value *= 127
            int_value = int(int_value)
            int_value = min(int_value, 127)
            int_value = max(int_value, 0)

            hi_value *= 127
            hi_value = int(hi_value)
            hi_value = min(hi_value, 127)
            hi_value = max(hi_value, 0)

            # shell_print(loeric_id, int_value, out_port)
            # prepare message
            if out_port is not None:
                msg = mido.Message(
                    "control_change",
                    value=int_value,
                    control=config["intensity_control_out"],
                )
                out_port.send(msg)
                msg = mido.Message(
                    "control_change",
                    value=hi_value,
                    control=config["human_impact_control_out"],
                )
                out_port.send(msg)

            df_values.loc[len(df_values)] = [
                now,
                loeric_id,
                "send",
                int_value,
                "intensity",
            ]
            df_values.loc[len(df_values)] = [
                now,
                loeric_id,
                "send",
                hi_value,
                "human_impact",
            ]

        except Exception as e:
            traceback.print_exception(e)
            exiting.set()
    df_action.to_csv("action_log.csv")
    df_values.to_csv("values_log.csv")
    all_dead.release()
    shell_print("Intensity Sync OFF.")


def sync_loeric(inports, outports):
    global songpos_wait, last_tempo, switch_timer, fix_sync_duration, stop_sync_duration, exiting, all_dead, config
    all_dead.acquire()
    shell_print("Sync ON.")
    pos_dict = {}
    updated_dict = defaultdict(bool)
    sleepers = []
    while not exiting.is_set():
        try:

            # awake sleeping loerics
            new_sleepers = []
            for s in sleepers:

                current = time.time()

                lid, start_time, wait_time, port, pos = s

                # if enough time has passed
                if current - start_time >= wait_time:
                    with port_lock:
                        pos_dict[lid] = (current, pos)
                        port.send(mido.Message("continue"))
                        # shell_print(re.search("#.*#", port.name)[0])
                        # shell_print(f"{lid}: AWAKEN at {pos}")
                        # shell_print()
                else:
                    # put them back
                    new_sleepers.append(s)

            sleepers = new_sleepers

            # receive message and port
            bundle = list(
                mido.ports.multi_receive(inports, yield_ports=True, block=False)
            )
            now = time.time()
            if len(bundle) == 0:
                continue
            port, msg = bundle[0]
            if msg.type != "songpos":
                continue

            # who sent this?
            loeric_id = re.search("#.*#", port.name)[0]
            # shell_print(f"{loeric_id}: SENT {msg.pos} ({now})")

            # don't sync the human
            if "HUMAN" in port.name:
                if (
                    # if first time
                    not loeric_id in pos_dict
                    # or skipped a beat
                    or now - pos_dict[loeric_id][0] > 2 * songpos_wait
                ):
                    positions = [t[1] for t in pos_dict.values()]
                    value = 0
                    if len(positions) != 0:
                        value = max(positions)
                    pos_dict[loeric_id] = (now, value)
                # only advance human position
                else:
                    pos_dict[loeric_id] = (now, pos_dict[loeric_id][1] + 1)
                    print(pos_dict)
                continue

            # check what position we should consider
            # store a tuple (time, position) for each
            pos_dict[loeric_id] = (now, msg.pos)

            # print(pos_dict)

            # agree on which position
            algorithm = config["tempo_policy"]["position"]
            if algorithm == "max":
                pos = max([t[1] for t in pos_dict.values()])
            elif algorithm == "min":
                pos = min([t[1] for t in pos_dict.values()])
            # shell_print(f"SYNC {pos}")

            # agree on what time
            timestamp = np.mean([t[0] for t in pos_dict.values() if t[1] == pos])

            # calculate difference in timestamp
            diff = now - timestamp

            fix_thr = fix_sync_duration
            stop_thr = stop_sync_duration

            # output port
            out_port = None
            for p in outports:
                if loeric_id == re.search("#.*#", p.name)[0]:
                    out_port = p
                    break

            # if tempo was updated before
            # we need to reset it to the original
            if updated_dict[loeric_id]:
                with port_lock:
                    send_tempo(last_tempo, out_port)
                updated_dict[loeric_id] = False

            # hard fix
            # stop and continue from next beat
            if diff >= stop_thr or msg.pos != pos:

                with port_lock:
                    # tell port to wait
                    out_port.send(mido.Message("stop"))
                    # tell port to start at next songpos
                    out_port.send(mido.Message("songpos", pos=pos + 1))

                # shell_print(f"{loeric_id}: SLEEP at {pos}")

                sleepers.append(
                    (loeric_id, now, songpos_wait - diff, out_port, pos + 1)
                )

            # soft fix
            # send a tempo bump
            elif diff >= fix_thr:
                # calculate the new tempo
                # so that we synchronize on the next beat
                q0 = timestamp + songpos_wait
                t0 = timestamp
                t1 = now
                f0q0 = last_tempo * q0
                f0t0 = last_tempo * t0
                new_tempo = round((f0q0 - f0t0) / (q0 - t1))

                with port_lock:
                    send_tempo(new_tempo, out_port)
                updated_dict[loeric_id] = True

            # shell_print("---------")

        except Exception as e:
            traceback.print_exception(e)
            exiting.set()
    all_dead.release()
    shell_print("Sync OFF.")


def shell_print(s):
    print(s)
    print("\033[1m\033[92;40mLOERIC >\033[0m", end=" ")


def close_shell():
    global songpos_wait, last_tempo, switch_timer, fix_sync_duration, stop_sync_duration, exiting, all_dead
    exiting.set()
    all_dead.acquire()
    all_dead.acquire()
    shell_print("Terminating.")


def check_args(command, num_args=0, values=[], optional=True):
    args = command.split(" ")
    if len(args) > num_args + 1 or (not optional and len(args) != num_args + 1):
        return False
    if optional and len(args) == 1:
        return True

    if len(values) != 0:
        for a in args[1:]:
            if not a in values:
                return False
    return True


def main():

    dir_path = os.path.dirname(os.path.realpath(__file__))

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default=f"{dir_path}/loeric_config/shell/config.json", type=str
    )
    args = parser.parse_args()
    args = vars(args)

    global config, sync_thread, intensity_thread

    # load base config
    with open(args["config"], "r") as f:
        config = json.load(f)

    update_tempo(120)
    sync_thread = threading.Thread()
    intensity_thread = threading.Thread()
    sync_ports_in = []
    sync_ports_out = []
    intensity_ports_in = []
    intensity_ports_out = []
    multi_out = None
    print("\033[1m\033[92;40mLOERIC >\033[0m", end=" ")
    try:
        while True:
            command = input()
            arg_0 = command.split(" ")[0]
            # connect to LOERIC ports
            if arg_0 == "dump":
                shell_print(config)
            elif arg_0 == "connect":
                if not check_args(
                    command, num_args=1, values=["in", "out"], optional=True
                ):
                    shell_print("Invalid argument.")
                    exiting.set()
                    all_dead.acquire()
                    all_dead.acquire()
                    exiting.clear()
                    all_dead.release(n=2)

                else:
                    arg = command.split(" ")[-1]
                    s = []

                    if arg == "in" or arg == "connect":
                        # ports to input messages from loeric
                        intensity_ports_in = [
                            mido.open_input(p)
                            for p in mido.get_input_names()
                            if "LOERIC out" in p or "HUMAN out" in p
                        ]
                        if len(intensity_ports_in) == 0:
                            s.append("No INT input to connect to.")
                        else:
                            s.append(
                                f"Opening ports:\n{intensity_ports_in}\nLOERIC INT 2 Shell connected."
                            )

                        # ports to input messages from loeric
                        sync_ports_in = [
                            mido.open_input(p)
                            for p in mido.get_input_names()
                            if "SYNC" in p
                        ]
                        if len(sync_ports_in) == 0:
                            s.append("No SYNC input to connect to.")
                        else:
                            s.append(
                                f"Opening ports:\n{sync_ports_in}\nLOERIC SYNC 2 Shell connected."
                            )

                    if arg == "out" or arg == "connect":
                        intensity_ports_out = [
                            mido.open_output(p)
                            for p in mido.get_output_names()
                            if "LOERIC in" in p or "HUMAN in" in p
                        ]
                        if len(intensity_ports_out) == 0:
                            s.append("No INT output to connect to.")
                        else:
                            s.append(
                                f"Opening ports:\n{intensity_ports_out}\nShell 2 LOERIC INT connected."
                            )

                        # ports to output messages to loeric
                        sync_ports_out = [
                            mido.open_output(p)
                            for p in mido.get_output_names()
                            if "LOERIC SYNC" in p
                        ]
                        if len(sync_ports_out) == 0:
                            s.append("No output to connect to.")
                        else:
                            multi_out = mido.ports.MultiPort(sync_ports_out)
                            s.append(
                                f"Opening ports:\n{sync_ports_out}\nShell 2 LOERIC SYNC connected."
                            )

                    s = "\n".join(s)
                    shell_print(s)

            # list ports
            elif arg_0 == "list":
                if not check_args(
                    command, num_args=1, values=["in", "out"], optional=True
                ):
                    shell_print("Invalid argument.")
                else:
                    arg = command.split(" ")[-1]
                    s = ""
                    if arg == "in" or arg == "list":
                        s += f"Inputs:\n{mido.get_input_names()}"
                    if arg == "out" or arg == "list":
                        if len(s) != 0:
                            s += "\n"
                        s += f"Outputs:\n{mido.get_output_names()}"
                    shell_print(s)
            # start and stop
            elif arg_0 in ["sync", "start", "stop", "continue"]:
                # start syncing
                s = []
                if command in ["start", "sync"]:
                    assert config["tempo_policy"]["position"] in ["min", "max"]
                    # kill sync thread
                    # this also kills the window thread
                    exiting.set()
                    all_dead.acquire()
                    all_dead.acquire()
                    exiting.clear()
                    all_dead.release(n=2)
                    if len(sync_ports_in) != 0 and len(sync_ports_out) != 0:
                        # create and start thread
                        sync_thread = threading.Thread(
                            target=sync_loeric, args=([sync_ports_in, sync_ports_out])
                        )
                        sync_thread.start()
                    else:
                        s.append("Could not start SYNC thread.")
                    if len(intensity_ports_in) != 0 and len(intensity_ports_out) != 0:
                        intensity_thread = threading.Thread(
                            target=sync_intensity,
                            args=([intensity_ports_in, intensity_ports_out]),
                        )
                        intensity_thread.start()
                    else:
                        s.append("Could not start INT thread.")

                    # reset termination flag
                if command != "sync" and multi_out is not None:
                    # send message
                    msg = mido.Message(command)
                    multi_out.send(msg)
                    s.append(str(msg))
                else:
                    s.append("Could not send command. Please connect to LOERIC first.")
                s = "\n".join(s)
                shell_print(s)
            # song position
            elif arg_0 == "songpos":
                if not check_args(command, num_args=1, values=[], optional=False):
                    shell_print("Invalid argument.")
                else:
                    if multi_out is not None:
                        cmd = "songpos"
                        try:
                            val = int(command.split(" ")[-1])
                            msg = mido.Message(cmd, pos=val)
                            multi_out.send(msg)
                            shell_print(msg)
                        except:
                            shell_print("Invalid argument.")
                    else:
                        shell_print("Please connect to LOERIC first.")
            # close shell
            elif arg_0 == "exit":
                close_shell()
                break
            # tempo change
            elif arg_0 == "tempo":
                if not check_args(
                    command,
                    num_args=1,
                    values=[str(n) for n in range(20, 301)],
                    optional=False,
                ):
                    shell_print(
                        "Invalid argument. Tempo value must be an integer between 20 and 300."
                    )
                else:
                    # get tempo
                    val = int(command.split(" ")[-1])
                    # update tempo info
                    update_tempo(val)
                    if sync_ports_out is not None:
                        for p in sync_ports_out:
                            send_tempo(val, p)
                    shell_print(f"Tempo set to {val}.")
            else:
                shell_print("Could not parse command.")
    except Exception as e:
        if type(e) is KeyboardInterrupt:
            close_shell()
        else:
            traceback.print_exception(e)
            close_shell()
