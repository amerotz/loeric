"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import argparse
import time

import mido

import loeric.loeric_utils as lu


def main() -> None:
    """
    Monitor the velocity of MIDI events on the specified port and send it as a control signal on the given output port.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="the input MIDI port.", type=int)
    parser.add_argument("-o", "--output", help="the output MIDI port.", type=int)
    parser.add_argument(
        "-vc",
        "--velocity-control",
        help="the control channel on which MPE velocity is sent.",
        type=int,
    )
    parser.add_argument(
        "-pc",
        "--pressure-control",
        help="the control channel on which MPE pressure is sent.",
        type=int,
    )
    parser.add_argument(
        "-tc",
        "--timbre-control",
        help="the control channel on which MPE timbre is sent.",
        type=int,
    )
    parser.add_argument(
        "-r",
        "--responsive",
        help="the weight of incoming values when computing intensity, in range 0 to 1.",
        type=float,
    )
    parser.add_argument(
        "--intonate", help="send intonation information", action="store_true"
    )
    args = parser.parse_args()

    inport, outport = lu.get_ports(
        input_number=args.input, output_number=args.output, list_ports=False
    )

    if outport is None:
        human_id = int(time.time())
        outport = mido.open_output(f"HUMAN out #{human_id}#", virtual=True)
    else:
        outport = mido.open_output(outport)

    if inport is None and outport is None:
        return
    velocity_intensity = 64
    pressure_intensity = 64
    timbre_intensity = 64

    try:
        print("Listening ...")
        with mido.open_input(inport) as port:
            for msg in port:
                message = msg.copy()

                # check if we care about the message
                if lu.is_note_on(msg):
                    velocity_intensity *= 1 - args.responsive
                    velocity_intensity += args.responsive * message.velocity

                    outport.send(
                        mido.Message(
                            "control_change",
                            channel=0,
                            control=args.velocity_control,
                            value=round(velocity_intensity),
                        )
                    )
                elif msg.type == "aftertouch":
                    pressure_intensity *= 1 - args.responsive
                    pressure_intensity += args.responsive * message.value

                    outport.send(
                        mido.Message(
                            "control_change",
                            channel=0,
                            control=args.pressure_control,
                            value=round(pressure_intensity),
                        )
                    )
                elif msg.type == "control_change" and msg.control == 74:
                    timbre_intensity *= 1 - args.responsive
                    timbre_intensity += args.responsive * message.value

                    outport.send(
                        mido.Message(
                            "control_change",
                            channel=0,
                            control=args.timbre_control,
                            value=round(timbre_intensity),
                        )
                    )

                print(
                    f"[VLTY]\t{round(velocity_intensity/127, 2)}\t[PRSR]\t{round(pressure_intensity/127, 2)}\t[TMBR]\t{round(timbre_intensity/127, 2)}"
                )
    except Exception as e:
        print(e)
        outport.close()
