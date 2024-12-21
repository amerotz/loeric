import mido
import threading
import time

current_pos = 0
done = threading.Event()


def sync_thread(inport, outport):
    print("Sync ON")
    global current_pos
    while not done.is_set():
        msg = inport.poll()
        if msg is None:
            time.sleep(1 / 10)
        else:
            print("Received", msg)
            if msg.type == "songpos":
                current_pos = 1 + max(msg.pos, current_pos)
            msg = mido.Message(cmd, pos=current_pos)
            outport.send(msg)
            print(msg)
    print("Sync OFF")


while True:
    command = input("\033[1m\033[92;40mLOERIC >\033[0m ")
    # connect to LOERIC ports
    if command.startswith("connect"):
        arg = command.split(" ")[-1]
        if arg == "in" or arg == "connect":
            # ports to input messages from loeric
            sync_ports_in = [
                mido.open_input(p)
                for p in mido.get_input_names()
                if "LOERIC SYNC out" in p
            ]
            if len(sync_ports_in) == 0:
                print("No input to connect to.")
            else:
                print("Opening ports", sync_ports_in)
                multi_in = mido.ports.MultiPort(sync_ports_in)
                print("LOERIC 2 Shell connected.")

        if arg == "out" or arg == "connect":
            # ports to output messages to loeric
            sync_ports_out = [
                mido.open_output(p)
                for p in mido.get_output_names()
                if "LOERIC SYNC in" in p
            ]
            if len(sync_ports_out) == 0:
                print("No output to connect to.")
            else:
                print("Opening ports", sync_ports_out)
                multi_out = mido.ports.MultiPort(sync_ports_out)
                print("Shell 2 LOERIC connected.")

        if arg not in ["in", "out", "connect"]:
            print("Could not parse command.")

    # sync songpos
    elif command == "sync":
        st = threading.Thread(target=sync_thread, args=(multi_in, multi_out))
        st.start()
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
    elif command in ["start", "stop"]:
        msg = mido.Message(command)
        multi_out.send(msg)
        done.set()
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
        print("Terminating.")
        break
    # tempo change
    elif command.startswith("tempo"):
        val = int(command.split(" ")[-1])
        msg = mido.Message(
            "clock",
            time=0,
        )
        for i in range(24):
            multi_out.send(msg)
            time.sleep((60 / val) / 24)
    else:
        print("Could not parse command.")
