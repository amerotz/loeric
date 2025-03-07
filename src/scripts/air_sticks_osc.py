import argparse
import threading
import numpy as np
import mido
import math
import time

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

sensor_min = 100000000
sensor_max = -100000000
sensor_value = 0


def read_sensor(control, out, responsiveness):
    def f(address, *osc_args):
        global sensor_min, sensor_max, sensor_value
        # print(f"{address}: {osc_args}")

        # energy based
        # the first three accelerometer values give you the energy of the system
        accel_energy = abs(osc_args[0] + osc_args[1] + osc_args[2])
        perc = responsiveness
        sensor_min = (1 - perc) * sensor_min + perc * min(sensor_min, accel_energy)
        sensor_max = (1 - perc) * sensor_max + perc * max(sensor_max, accel_energy)
        sensor_value = min(
            max((accel_energy - sensor_min) / (sensor_max - sensor_min), 0), 1
        )
        sensor_value = (1 - perc) * sensor_value + perc * sensor_value
        # print(sensor_value)

    return f


def default_handler(address, *args):
    # print(f"DEFAULT {address}: {args}")
    print(f"Unknown message {address}")


def send_control(out, args):
    while True:
        global sensor_value
        value = int(127 * sensor_value)
        out.send(
            mido.Message(
                "control_change",
                channel=0,
                control=args.control,
                value=value,
            )
        )
        print(args.port, args.control, value, sep="\t")
        time.sleep(0.1)


def main(args):
    with mido.open_output(mido.get_output_names()[args.port]) as out:
        t = threading.Thread(target=send_control, args=(out, args))
        t.start()
        dispatcher = Dispatcher()
        dispatcher.map(
            args.message, read_sensor(args.control, out, args.responsiveness)
        )
        dispatcher.set_default_handler(default_handler)

        ip = args.server
        port = args.osc_port

        server = BlockingOSCUDPServer((ip, port), dispatcher)

        server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=None)
    # message /1/CombinedDataPacket is sensor 1, /2/CombinedDataPacket sensor
    parser.add_argument("-m", "--message", type=str, default="/1/CombinedDataPacket")
    parser.add_argument("-r", "--responsiveness", type=float, default=0.85)
    parser.add_argument("-op", "--osc-port", type=int, default=None)
    parser.add_argument("-c", "--control", type=int, default=None)
    parser.add_argument("-s", "--server", type=str, default="127.0.0.1")

    args = parser.parse_args()
    main(args)
