import contour as cnt
import tune as tu
import groover as gr


# play midi file
def play(tune: tu.Tune, out, args) -> None:
    """
    Play the given tune.

    :param tune: the tune to play
    :param out: the output midi port
    :param args: the performance arguments
    """
    # create groover

    groover = gr.Groover(tune)

    # repeat as specified
    for t in range(args.repeat):
        print(f"Repetition {t+1}/{args.repeat}")
        # iterate over messages
        for message in tune:
            if not message.is_meta:
                # make the groover play the messages
                new_messages = groover.perform(message)

                for msg in new_messages:
                    time.sleep(msg.time)
                    out.send(msg)

    print("Playback terminated.")


def main(args):
    # list ports
    if args.list_ports:
        print("Available inputs:")
        for i, p in enumerate(mido.get_input_names()):
            print(f"{i}:\t{p}")
        print()
        print("Available outputs:")
        for i, p in enumerate(mido.get_output_names()):
            print(f"{i}:\t{p}")
        return

    # if no input is defined
    if args.input is None:
        print()
        for i, m in enumerate(mido.get_input_names()):
            print(f"{i} : {m}")
        in_index = int(input("Choose input midi port:"))
        print()
    else:
        in_index = args.input

    # if no output is defined
    if args.output is None:
        for i, m in enumerate(mido.get_output_names()):
            print(f"{i} : {m}")
        out_index = int(input("Choose output midi port:"))
    else:
        out_index = args.output

    # get the ports
    inport = mido.get_input_names()[in_index]
    outport = mido.get_output_names()[out_index]

    # consistency with MIDI spec and mido
    args.midi_channel -= 1

    # open in
    with mido.open_input(inport) as port:
        # open out
        with mido.open_output(outport) as out:
            if not args.no_prompt and not args.save:
                input("Press any key to start playback:")

            # start the player thread
            try:
                # load a tune
                tune = tu.Tune(args.source)
                t = threading.Thread(target=play, args=(tune, out, args))
                t.start()
                t.join()

            except KeyboardInterrupt:
                print("Playback stopped by user.")
                print("Attempting graceful shutdown...")
                # make sure to turn off all notes
                for i in range(128):
                    out.send(
                        mido.Message(
                            "note_off", note=i, velocity=0, channel=args.midi_channel
                        )
                    )
                print("Done.")
                return


if __name__ == "__main__":
    import argparse
    import mido
    import threading
    import traceback
    import time

    # args
    parser = argparse.ArgumentParser()
    parser.add_argument("--list_ports", action="store_true")
    parser.add_argument("source", nargs="?", default="")
    parser.add_argument("-c", "--control", type=int)
    parser.add_argument("-i", "--input", type=int)
    parser.add_argument("-o", "--output", type=int)
    parser.add_argument("-sw", "--speed_warp", type=float, default=0.1)
    parser.add_argument("-cc", "--cut_chance", type=float, default=1)
    parser.add_argument("-dc", "--drop_chance", type=float, default=0.1)
    parser.add_argument("-rc", "--roll_chance", type=float, default=1)
    parser.add_argument("-sc", "--slide_chance", type=float, default=1)
    parser.add_argument("-hi", "--human_impact", type=float, default=0)
    parser.add_argument("-mc", "--midi-channel", type=int, default=1)
    parser.add_argument("-t", "--transpose", type=int, default=0)
    parser.add_argument("-r", "--repeat", type=int, default=1)
    parser.add_argument("-bpm", type=int, default=None)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--random", action="store_true")
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()

    main(args)
