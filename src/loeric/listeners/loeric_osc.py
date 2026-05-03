"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import argparse

import mido
import numpy as np
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


args = None


def send_control(control, out):
    def f(address, *osc_args):
        print(f"{address}: {osc_args}")
        value = int(127 * np.array(osc_args).mean())
        out.send(
            mido.Message(
                "control_change",
                channel=0,
                control=control,
                value=value,
            )
        )
        print(args.port, args.control, value, sep="\t")
        # time.sleep(0.25)

    return f


def default_handler(address, *args):
    # print(f"DEFAULT {address}: {args}")
    print(f"Unknown message {address}")


def main():
    global args
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
