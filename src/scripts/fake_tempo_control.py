"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import argparse
import time

import mido

# generate a fake control signal


def main(args):
    sync_ports_out = [
        mido.open_output(p) for p in mido.get_output_names() if "LOERIC SYNC" in p
    ]
    out = mido.ports.MultiPort(sync_ports_out)
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
            """
            if i % 36 == 0:
                print("Beat")
            n = 72
            if i % n == 0:
                print("pos", i // n)
                out.send(
                    mido.Message(
                        "songpos",
                        pos=i // n,
                        time=0,
                    )
                )
            """
            i += 1
    except KeyboardInterrupt:
        if args.kill:
            out.send(mido.Message("reset", time=0))
        print("Stopping.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, default=None)
    parser.add_argument("-t", "--tempo", type=int, default=120)
    parser.add_argument("-k", "--kill", default=False, action="store_true")

    args = parser.parse_args()

    print(args.tempo)
    main(args)
