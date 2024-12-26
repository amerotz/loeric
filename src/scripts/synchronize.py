import mido
import math
import threading
import time
from collections import defaultdict


def update_tempo(tempo):
    global last_tempo, sync_duration, songpos_wait
    last_tempo = tempo
    sync_duration = 0.25 * 60 / last_tempo
    songpos_wait = 2 * 60 / last_tempo


last_tempo = 120
sync_duration = 0.25 * 60 / last_tempo
songpos_wait = 2 * 60 / last_tempo
pos_dict = defaultdict(float)
exiting = threading.Event()
sync_thread = None
port_lock = threading.Lock()
tempo_lock = threading.Lock()


def sync_loeric(inports, outports):
    global sync_duration, pos_dict, exiting
    print("Sync ON.")
    while not exiting.is_set():
        try:

            # receive message and port
            with port_lock:
                bundle = list(
                    mido.ports.multi_receive(inports, yield_ports=True, block=False)
                )
            if len(bundle) == 0:
                continue
            port, msg = bundle[0]
            now = time.time()
            if msg.type != "songpos":
                continue
            pos = msg.pos

            # update time for position if greater
            if pos not in pos_dict:
                pos_dict[pos] = now
                continue

            # if difference in songpos is more than one eigth
            diff = now - pos_dict[pos]
            print(diff, sync_duration)

            # obtain output port
            loeric_id = port.name.split("#")[1]
            out_port = None
            for p in outports:
                if loeric_id == p.name.split("#")[1]:
                    out_port = p
                    break

            # fix timing
            if diff >= sync_duration:

                # tell port to wait
                out_port.send(mido.Message("stop"))

                # conpensate duration
                # songpos messages are sent every
                # half-note at current tempo
                multiplier = math.ceil(diff / songpos_wait)
                print(songpos_wait - diff, multiplier)
                time.sleep(multiplier * songpos_wait - diff)

                # tell port to start at next songpos
                out_port.send(mido.Message("songpos", pos=msg.pos + multiplier))
                out_port.send(mido.Message("continue"))

        except Exception as e:
            print(e)
            exiting.set()
    print("\nSync OFF.")


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
                if sync_thread is not None and sync_thread.is_alive():
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
    elif command in ["start", "stop", "continue"]:
        # start syncing
        if command == "start":
            # reset positions
            pos_dict = defaultdict(float)
            # if thread is dead
            if sync_thread is None or not sync_thread.is_alive():
                # reset termination flag
                exiting.clear()
                # create and start thread
                sync_thread = threading.Thread(
                    target=sync_loeric, args=([sync_ports_in, sync_ports_out])
                )
                sync_thread.start()
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
