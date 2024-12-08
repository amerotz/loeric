import loeric.loeric_utils as lu
import threading
import time
import mido
import argparse


def main() -> None:
    """
    Monitor the velocity of MIDI events on the specified ports, combined them and send a control signal on the given output port.

    :param args: the performance arguments.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list_ports",
        help="list available input and output MIDI ports and exit.",
        action="store_true",
    )
    parser.add_argument("-i1", "--input_1", help="the first input MIDI port.", type=int)
    parser.add_argument(
        "-i2", "--input_2", help="the second input MIDI port.", type=int
    )
    parser.add_argument("-o", "--output", help="the output MIDI port.", type=int)
    parser.add_argument(
        "-i1c",
        "--input-1-control",
        help="the control channel on which input 1 intensity is sent.",
        type=int,
    )
    parser.add_argument(
        "-i2c",
        "--input-2-control",
        help="the control channel on which input 2 intensity is sent.",
        type=int,
    )
    parser.add_argument(
        "-c",
        "--control",
        help="the control channel on which output intensity is sent.",
        type=int,
    )
    parser.add_argument(
        "-m",
        "--mode",
        help="how the two inputs should be combined.",
        type=str,
    )
    args = parser.parse_args()

    values = {}
    done_listening = False

    def listen_to_port(port, control):
        with mido.open_input(port) as inport:
            for message in inport:
                if message.is_cc() and message.control == control:
                    values[port] = message.value
                if done_listening:
                    break
        print(f"Terminating {port} listener.")

    aggregators = {
        "sum": lambda x, y: x + y,
        "diff": lambda x, y: x - y,
        "mean": lambda x, y: (x + y) / 2,
        "max": lambda x, y: max(x, y),
        "min": lambda x, y: min(x, y),
    }

    input_1 = mido.get_input_names()[args.input_1]
    input_2 = mido.get_input_names()[args.input_2]
    output = mido.get_output_names()[args.output]
    intensity = 64

    values[input_1] = 64
    values[input_2] = 64

    t1 = threading.Thread(target=listen_to_port, args=(input_1, args.input_1_control))
    t2 = threading.Thread(target=listen_to_port, args=(input_2, args.input_2_control))
    t1.start()
    t2.start()

    try:
        with mido.open_output(output) as out:
            while True:
                v1 = values[input_1]
                v2 = values[input_2]
                value = aggregators[args.mode](v1, v2)
                value = min(127, value)
                value = max(0, value)
                value = int(value)
                print(v1, v2, value, sep="\t")

                message = mido.Message(
                    "control_change", channel=0, control=args.control, value=value
                )

                out.send(message)
                time.sleep(1 / 10)
    except KeyboardInterrupt as e:
        done_listening = True
        print(e)
