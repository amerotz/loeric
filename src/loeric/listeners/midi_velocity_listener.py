import loeric.loeric_utils as lu
import mido
import argparse


def main() -> None:
    """
    Monitor the velocity of MIDI events on the specified port and send it as a control signal on the given output port.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="the input MIDI port.", type=int)
    parser.add_argument("-o", "--output", help="the output MIDI port.", type=int)
    parser.add_argument(
        "-c",
        "--control",
        help="the control channel on which intensity is sent.",
        type=int,
    )
    parser.add_argument(
        "-r",
        "--responsive",
        help="the weight of incoming values when computing intensity, in range 0 to 1.",
        type=float,
    )
    args = parser.parse_args()

    inport, outport = lu.get_ports(
        input_number=args.input, output_number=args.output, list_ports=False
    )
    if inport is None and outport is None:
        return
    intensity = 64

    with mido.open_output(outport) as out:
        with mido.open_input(inport) as port:
            for msg in port:
                message = msg.copy()

                # check if we care about the message
                if lu.is_note_on(msg):
                    intensity *= 1 - args.responsive
                    intensity += args.responsive * message.velocity

                    print(f"INT:{round(intensity/127, 2)}")
                    out.send(
                        mido.Message(
                            "control_change",
                            channel=0,
                            control=args.control,
                            value=round(intensity),
                        )
                    )

                out.send(message)
