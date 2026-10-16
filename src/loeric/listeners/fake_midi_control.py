import argparse
import numpy as np
import mido
import math
import time


# generate a fake control signal
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o", "--output", type=int, default=None, help="the output port."
    )
    parser.add_argument(
        "-c",
        "--control",
        type=int,
        default=11,
        help="the MIDI control change message to send",
    )
    parser.add_argument(
        "-p",
        "--period",
        type=float,
        default=1,
        help="the period of the sine function in seconds.",
    )
    parser.add_argument(
        "-m",
        "--messages-per-second",
        type=float,
        default=4,
        help="how many messages per second should be sent",
    )

    args = parser.parse_args()
    with mido.open_output(mido.get_output_names()[args.output]) as out:
        while True:
            # send a message every 0.25 seconds
            value = round(
                127 * (math.sin(2 * np.pi * time.time() / args.period) + 1) / 2
            )
            out.send(
                mido.Message(
                    "control_change",
                    channel=0,
                    control=args.control,
                    value=value,
                )
            )
            print(args.output, args.control, value, sep="\t")
            time.sleep(1 / args.messages_per_second)
