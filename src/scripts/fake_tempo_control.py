import argparse
import mido
import math
import time

# generate a fake control signal


def main(args):
    with mido.open_output(mido.get_output_names()[args.port]) as out:
        try:
            out.send(mido.Message("start", time=0))
            i = 0
            while True:
                # send a message every 0.25 seconds
                out.send(
                    mido.Message(
                        "clock",
                        time=0,
                    )
                )
                time.sleep((60 / args.tempo) / 24)
                i += 1
                if i % 24 == 0:
                    print("Beat")
        except KeyboardInterrupt:
            out.send(mido.Message("reset", time=0))
            print("Stopping.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=None)
    parser.add_argument("-t", "--tempo", type=int, default=120)

    args = parser.parse_args()

    print(args.tempo)
    main(args)
