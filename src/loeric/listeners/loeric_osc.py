import argparse
import numpy as np
import mido
import math
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


def send_control(control, out):
    def f(address, *osc_args):
        # print(f"{address}: {osc_args}")
        value = int(127 * np.array(osc_args).mean())
        out.send(
            mido.Message(
                "control_change",
                channel=0,
                control=control,
                value=value,
            )
        )
        global args
        print(args.port, args.control, value, sep="\t")
        # time.sleep(0.25)

    return f


def default_handler(address, *args):
    # print(f"DEFAULT {address}: {args}")
    print(f"Unknown message {address}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=None)
    parser.add_argument("-m", "--message", type=str, default="/loeric/control")
    parser.add_argument("-op", "--osc-port", type=int, default=None)
    parser.add_argument("-c", "--control", type=int, default=None)
    parser.add_argument("-s", "--server", type=str, default="127.0.0.1")

    args = parser.parse_args()
    with mido.open_output(mido.get_output_names()[args.port]) as out:
        dispatcher = Dispatcher()
        dispatcher.map(args.message, send_control(args.control, out))
        dispatcher.set_default_handler(default_handler)

        ip = args.server
        port = args.osc_port

        server = BlockingOSCUDPServer((ip, port), dispatcher)

        server.serve_forever()
