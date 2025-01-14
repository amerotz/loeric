import mido
import numpy as np
import re
import math
import threading
import random
import time
import traceback
from collections import defaultdict


last_tempo = 120
fix_sync_duration = 0
stop_sync_duration = 0
songpos_wait = 0
exiting = threading.Event()
switch_timer = 0
sync_thread = None
intensity_thread = None
port_lock = threading.Lock()
all_dead = threading.Semaphore(value=2)


def send_tempo(tempo, port):
    tup = []
    while tempo > 0:
        v = min(tempo, 127)
        tup.append(v)
        tempo -= v
    msg = mido.Message("sysex", data=tuple(tup))
    port.send(msg)


def update_tempo(tempo):
    global last_tempo, stop_sync_duration, fix_sync_duration, songpos_wait, switch_timer
    last_tempo = tempo
    fix_sync_duration = 0.0625 * 60 / last_tempo
    stop_sync_duration = 0.5 * 60 / last_tempo
    songpos_wait = 1 * 60 / last_tempo
    switch_timer = 20 * songpos_wait


def sync_intensity(inports, outports):
    global exiting, switch_timer, all_dead
    all_dead.acquire()
    shell_print("Intensity Sync ON.")
    int_dict = {}
    action_dict = {}
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
            if msg.type != "control_change" or msg.control != 69:
                continue

            # who sent this?
            loeric_id = re.search("#.*#", port.name)[0]

            # keep track of intensity
            int_dict[loeric_id] = msg.value

            # don't consider human for actions
            if "HUMAN" in port.name:
                continue

            now = time.time()
            if loeric_id not in action_dict:
                action_dict[loeric_id] = (now, "match", loeric_id)
                print("added")

            diff = now - action_dict[loeric_id][0]
            # choose new action
            if diff >= switch_timer:

                players = [p for p in int_dict.keys() if str(p) != loeric_id]
                # backoff or
                # match
                # any group of players
                action = random.choice(["listen", "invert"])
                n = 1
                if len(players) < 1:
                    continue
                elif len(players) > 1:
                    n = random.randint(1, len(players))
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
            # send intensity signal according to action
            value = np.mean([int_dict[p] for p in group])
            if action == "invert":
                value = 127 - value

            value = int(value)
            value = min(value, 127)
            value = max(value, 0)

            # shell_print(loeric_id, value, out_port)
            # prepare message
            if out_port is not None:
                msg = mido.Message("control_change", value=value, control=42)
                out_port.send(msg)

        except Exception as e:
            traceback.print_exception(e)
            exiting.set()
    all_dead.release()
    shell_print("Intensity Sync OFF.")


def sync_loeric(inports, outports):
    global stop_sync_duration, fix_sync_duration, exiting, last_tempo, num_clocks, all_dead, songpos_wait
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

            # check what position we should consider
            # store a tuple (time, position) for each
            pos_dict[loeric_id] = (now, msg.pos)

            # agree on which position
            pos = max([t[1] for t in pos_dict.values()])
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
    global exiting, all_dead
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
    update_tempo(last_tempo)
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
            if arg_0 == "connect":
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
                            if "LOERIC SYNC" in p
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
