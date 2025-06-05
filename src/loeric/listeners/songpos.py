import mido
import argparse
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="the input MIDI port.", type=int)
    parser.add_argument(
        "-o", "--output", help="the output MIDI port.", type=int, default=None
    )

    parser.add_argument(
        "-p",
        "--positions",
        help="the list of positions to jump to.",
        type=lambda x: [int(num) for num in x.split(",")],
        default=None,
    )
    args = parser.parse_args()

    positions = args.positions

    id = int(time.time())
    with mido.open_output(mido.get_output_names()[args.output]) as out:
        with mido.open_input(mido.get_input_names()[args.input]) as in_:
            i = -1
            print("Awaiting message...")
            while True:
                msg = in_.receive()
                if msg.control != 66:
                    continue
                if msg.value == 127:
                    continue

                if i == -1:
                    print("Sending START")
                    msg = mido.Message("start")
                    out.send(msg)

                i += 1

                if i >= len(positions):
                    print("No other position specified. Terminating.")
                    break

                pos = positions[i]
                print(f"Switching to position {pos}")
                msg = mido.Message("stop")
                out.send(msg)

                msg = mido.Message("songpos", pos=pos)
                out.send(msg)

                msg = mido.Message("continue")
                out.send(msg)
