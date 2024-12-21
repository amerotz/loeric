import argparse
import mido
import math
import time


# generate a fake control signal
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=None)
    parser.add_argument("-c", "--control", type=int, default=None)

    args = parser.parse_args()
    with mido.open_output(mido.get_output_names()[args.port]) as out:
        while True:
            # send a message every 0.25 seconds
            value = round(127 * (math.sin(time.time()) + 1) / 2)
            out.send(
                mido.Message(
                    "control_change",
                    channel=0,
                    control=args.control,
                    value=value,
                )
            )
            print(args.port, args.control, value, sep="\t")
            time.sleep(0.25)
