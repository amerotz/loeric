import mido
import numpy as np
import re
import math
import threading
import time
import traceback
from collections import defaultdict


last_tempo = 120
sync_duration = 0
songpos_wait = 0
min_window_size = 0.1
max_window_size = 0.25
window_size = max_window_size
exiting = threading.Event()
increase_window = threading.Event()
sync_thread = None
port_lock = threading.Lock()
window_lock = threading.Lock()


def update_tempo(tempo):
    global last_tempo, sync_duration, songpos_wait, window_size, window_lock
    last_tempo = tempo
    sync_duration = window_size * 60 / last_tempo
    songpos_wait = 1 * 60 / last_tempo


def sync_loeric(inports, outports):
    global sync_duration, exiting, min_window_size, window_size, last_tempo
    print("\nSync ON.")
    pos_dict = {}
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
                        # print(re.search("#.*#", port.name)[0])
                        # print(f"{lid}: AWAKEN at {pos}")
                        # print()
                else:
                    # put them back
                    new_sleepers.append(s)

            sleepers = new_sleepers

            # receive message and port
            with port_lock:
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
            # print(f"{loeric_id}: SENT {msg.pos} ({now})")

            # check if pending old message
            # and ignore in case
            if loeric_id in pos_dict and pos_dict[loeric_id][1] >= msg.pos:
                print(f"OLD POSITION {msg.pos} FROM {loeric_id}")
                print("---------")
                continue

            # check what position we should consider
            # store a tuple (time, position) for each
            pos_dict[loeric_id] = (now, msg.pos)

            # agree on which position
            pos = max([t[1] for t in pos_dict.values()])
            # print(f"SYNC {pos}")

            # agree on what time
            timestamp = np.mean([t[0] for t in pos_dict.values() if t[1] == pos])

            # calculate difference in timestamp
            diff = now - timestamp

            with window_lock:
                thr = sync_duration
                win = window_size
                print(window_size)
            # fix timing
            if diff >= thr or msg.pos != pos:

                # output port
                out_port = None
                for p in outports:
                    if loeric_id == re.search("#.*#", p.name)[0]:
                        out_port = p
                        break

                with port_lock:
                    # tell port to wait
                    out_port.send(mido.Message("stop"))
                    # tell port to start at next songpos
                    out_port.send(mido.Message("songpos", pos=pos + 1))

                # print(f"{loeric_id}: SLEEP at {pos}")

                sleepers.append(
                    (loeric_id, now, songpos_wait - diff, out_port, pos + 1)
                )

                min_window_size = win

                # if things are out of time, give more slack
                increase_window.set()

            # print("---------")

        except Exception as e:
            traceback.print_exception(e)
            exiting.set()
    print("\nSync OFF.")


def congestion_control():
    """
    Handle the congestion window.
    """
    global window_size, min_window_size, max_window_size
    while not exiting.is_set():
        with window_lock:
            if increase_window.is_set():
                window_size *= 2
                increase_window.clear()
            else:
                # if things are smooth, increase precision
                if window_size <= min_window_size:
                    min_window_size -= 0.0001
                window_size -= 0.001

            window_size = max(window_size, min_window_size, 0.1)
            window_size = min(window_size, max_window_size)

            update_tempo(last_tempo)
        time.sleep(songpos_wait / 10)


update_tempo(last_tempo)
sync_thread = threading.Thread()
window_thread = threading.Thread()
while True:
    command = input("\033[1m\033[92;40mLOERIC >\033[0m ")
    # connect to LOERIC ports
    if command.startswith("connect"):
        arg = command.split(" ")[-1]

        if arg == "in" or arg == "connect":
            # ports to input messages from loeric
            sync_ports_in = [
                mido.open_input(p) for p in mido.get_input_names() if "LOERIC SYNC" in p
            ]
            if len(sync_ports_in) == 0:
                print("No input to connect to.")
            else:
                print("Opening ports", sync_ports_in)
                # multi_in = mido.ports.MultiPort(sync_ports_in)
                print("LOERIC 2 Shell connected.")
                # stop the sync thread
                # next call to start will start it again
                exiting.set()

        if arg == "out" or arg == "connect":
            # ports to output messages to loeric
            sync_ports_out = [
                mido.open_output(p)
                for p in mido.get_output_names()
                if "LOERIC SYNC" in p
            ]
            if len(sync_ports_out) == 0:
                print("No output to connect to.")
            else:
                print("Opening ports", sync_ports_out)
                multi_out = mido.ports.MultiPort(sync_ports_out)
                print("Shell 2 LOERIC connected.")

        if arg not in ["in", "out", "connect"]:
            print("Could not parse command.")

    # list ports
    elif command == "list":
        arg = command.split(" ")[-1]
        if arg == "in" or arg == "list":
            print("Inputs:")
            print(mido.get_input_names())
        if arg == "out" or arg == "list":
            print("Outputs:")
            print(mido.get_output_names())
    # start and stop
    elif command in ["sync", "start", "stop", "continue"]:
        # start syncing
        if command in ["start", "sync"]:
            # kill sync thread
            # this also kills the window thread
            exiting.set()
            # create and start thread
            sync_thread = threading.Thread(
                target=sync_loeric, args=([sync_ports_in, sync_ports_out])
            )
            sync_thread.start()
            # reset termination flag
            exiting.clear()
            # start window_thread
            increase_window.clear()
            window_thread = threading.Thread(target=congestion_control)
            window_thread.start()
        if command != "sync":
            # send message
            msg = mido.Message(command)
            multi_out.send(msg)
            print(msg)
    # song position
    elif command.startswith("songpos"):
        cmd = "songpos"
        val = int(command.split(" ")[-1])
        msg = mido.Message(cmd, pos=val)
        multi_out.send(msg)
        print(msg)
    # close shell
    elif command == "exit":
        exiting.set()
        print("Terminating.")
        break
    # tempo change
    elif command.startswith("tempo"):
        # get tempo
        val = int(command.split(" ")[-1])
        # update tempo info
        update_tempo(val)
        # prepare message
        msg = mido.Message(
            "clock",
            time=0,
        )
        # send a tick
        with port_lock:
            sleep_time = (60 / val) / 24
            for p in sync_ports_out:
                for i in range(24):
                    p.send(msg)
                    time.sleep(sleep_time)
    else:
        print("Could not parse command.")
