import contour as cnt
import tune as tu
import groover as gr
import player as pl


# play midi file
def play(out, args) -> None:
    """
    Play the given tune.

    :param out: the output midi port
    :param args: the performance arguments
    """

    # load a tune
    tune = tu.Tune(args.source)

    # create groover
    groover = gr.Groover(
        tune,
        bpm=args.bpm,
        random_weight=0.2,
        human_impact=args.human_impact,
        config_file=args.config,
    )

    # create player
    player = pl.Player(
        tempo=groover.tempo,
        key_signature=tune.key_signature,
        time_signature=tune.time_signature,
        save=args.save,
        midi_out=out,
    )

    # repeat as specified
    for t in range(args.repeat):
        print(f"Repetition {t+1}/{args.repeat}")
        # iterate over messages
        for message in tune.events():
            if not message.is_meta:
                # make the groover play the messages
                new_messages = groover.perform(message)
                player.play(new_messages)

        # reset the groover at the end of the repetition
        groover.reset()

    if args.save:
        player.save(f"generated_{args.source}.mid")

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
    port = mido.open_input(inport)
    # open out
    if args.save:
        out = None
    else:
        out = mido.open_output(outport)

    if args.no_prompt or (not args.save):
        input("Press any key to start playback:")

    # start the player thread
    try:
        p = multiprocessing.Process(target=play, args=(out, args))
        p.start()
        p.join()

    except KeyboardInterrupt:
        print("Playback stopped by user.")
        print("Attempting graceful shutdown...")
        p.terminate()
        # make sure to turn off all notes
        for i in range(128):
            out.send(
                mido.Message("note_off", note=i, velocity=0, channel=args.midi_channel)
            )
        print("Done.")
        port.close()
        out.close()
        sys.exit()


if __name__ == "__main__":
    import argparse
    import mido
    import multiprocessing
    import traceback
    import sys
    import time

    # args
    parser = argparse.ArgumentParser()
    parser.add_argument("--list_ports", action="store_true")
    parser.add_argument("source", nargs="?", default="")
    # parser.add_argument("-c", "--control", type=int)
    parser.add_argument("-hi", "--human_impact", type=float, default=0)
    parser.add_argument("-i", "--input", type=int)
    parser.add_argument("-o", "--output", type=int)
    parser.add_argument("-mc", "--midi-channel", type=int, default=1)
    parser.add_argument("-t", "--transpose", type=int, default=0)
    parser.add_argument("-r", "--repeat", type=int, default=1)
    parser.add_argument("-bpm", type=int, default=None)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--no-prompt", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    # parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()

    main(args)
