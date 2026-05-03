"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import argparse

import mido


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="the input MIDI port.", type=int)
    parser.add_argument(
        "-o", "--output", help="the output MIDI port.", type=int, default=None
    )
    parser.add_argument(
        "-c",
        "--control",
        help="the control change number to monitor.",
        type=int,
        default=66,
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

    with mido.open_output(mido.get_output_names()[args.output]) as out:
        with mido.open_input(mido.get_input_names()[args.input]) as in_:
            i = -1
            print("Awaiting message...")
            while True:
                msg = in_.receive()
                if msg.control != args.control:
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
