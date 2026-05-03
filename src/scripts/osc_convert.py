"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import argparse

import mido
from pythonosc.udp_client import SimpleUDPClient


def main(args):

    client = SimpleUDPClient(args.server, args.port)  # Create client

    inport = mido.open_input(mido.get_input_names()[args.input])

    active_notes = []
    commands = {1: "intensity", 2: "brightness", 3: "harmonic"}

    def translate_messages(message):
        if message.type == "note_on":

            active_notes.append(message.note)

            print(f"/mrp/midi {message.bytes()}")

            client.send_message("/mrp/midi", message.bytes())

            if args.velocity2intensity:
                client.send_message(
                    "/mrp/quality/intensity", [15, message.note, message.velocity / 127]
                )

                print(f"/mrp/intensity {[15, message.note, message.velocity/127]}")

            if args.velocity2harmonic:
                client.send_message(
                    "/mrp/quality/harmonic", [15, message.note, message.velocity / 127]
                )

                print(f"/mrp/harmonic{[15, message.note, message.velocity/127]}")

        elif message.type == "note_off":
            active_notes.remove(message.note)

            client.send_message("/mrp/midi", message.bytes())
            print(f"/mrp/midi {message.bytes()}")

        elif message.type == "control_change":

            # all notes off
            if message.control == 123:
                client.send_message("/mrp/allnotesoff", message.bytes)
                print(f"all notes off")
                return

            value = message.value / 127.0

            # these are always in the format
            # MIDI Channel, Note Number, Value
            # int int float
            # MIDI Channel is always 15
            # TODO handle which note is affected

            # intensity
            message_type = commands[message.control]

            if not args.last_note_only:
                for note in active_notes:
                    client.send_message(
                        f"/mrp/quality/{message_type}",
                        [15, note, value],
                    )
                    print(f"/mrp/{message_type} {[15, note, value]}")
            else:
                client.send_message(
                    f"/mrp/quality/{message_type}",
                    [15, translate_messages.last_note, value],
                )
                print(
                    f"/mrp/{message_type} {[15, translate_messages.last_note, value]}"
                )

        print()

    inport.callback = translate_messages
    translate_messages.last_note = 0

    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Terminating.")
        inport.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=int, default=None)
    parser.add_argument("-p", "--port", type=int, default=None)
    parser.add_argument("-s", "--server", type=str, default="127.0.0.1")
    parser.add_argument("-v2i", "--velocity2intensity", action="store_true")
    parser.add_argument("-v2h", "--velocity2harmonic", action="store_true")
    parser.add_argument("-lno", "--last_note_only", action="store_true")

    args = parser.parse_args()
    main(args)
