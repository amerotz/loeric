import contour as cnt
import tune as tu
import groover as gr
import player as pl
import loeric_utils as lu

from collections.abc import Callable


# play midi file
def play(groover, tune, out, args) -> None:
    """
    Play the given tune with the given groover.

    :param groover: the groover object
    :param tune: the tune object
    :param out: the output midi port
    :param args: the performance arguments
    """
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
        name = os.path.splitext(os.path.basename(args.source))[0]
        if args.output_dir is None:
            dirname = os.path.dirname(args.source)
        else:
            if not os.path.isdir(args.output_dir):
                os.makedirs(args.output_dir)
            dirname = args.output_dir
        player.save(f"{dirname}/generated_{name}_{args.seed}.mid")

    print("Playback terminated.")


def check_midi_control(
    groover: gr.Groover, control2contour: dict[int, str]
) -> Callable[[], None]:
    """
    Returns a function that associates a contour name (values) for every MIDI control number in the dictionary (keys) and updates the groover accordingly.
    The value of the contour will be the control value mapped in the interval [0, 1].

    :param groover: the groover object.
    :param control2contour: a dictionary of control numbers associated to contour names.

    :return: a callback function that will check for the given values.
    """

    def callback(msg):
        for event_number in control2contour:
            if msg.is_cc(event_number):
                contour_name = control2contour[event_number]
                value = msg.value / 127
                groover.set_contour_value(contour_name, value)
                print(f"{contour_name}: {round(value, 2)}")

    return callback


def main(args):
    inport, outport = lu.get_ports(
        input_number=args.input, output_number=args.output, list_ports=args.list_ports
    )
    if inport is None and outport is None:
        return

    # open in
    if inport is not None:
        port = mido.open_input(inport)
    else:
        port = None

    # open out
    if args.save or outport is None:
        out = None
    else:
        out = mido.open_output(outport)

    # consistency with MIDI spec and mido
    args.midi_channel -= 1

    if (not args.no_prompt) and (not args.save):
        input("Press any key to start playback:")

    # start the player thread
    try:
        # load a tune
        tune = tu.Tune(args.source)

        # create groover
        groover = gr.Groover(
            tune,
            bpm=args.bpm,
            midi_channel=args.midi_channel,
            transpose=args.transpose,
            diatonic_errors=args.diatonic,
            random_weight=0.2,
            human_impact=args.human_impact,
            seed=args.seed,
            config_file=args.config,
        )

        # set input callback
        if port is not None:
            port.callback = check_midi_control(groover, {args.control: "human"})

        player_thread = threading.Thread(target=play, args=(groover, tune, out, args))
        player_thread.start()
        player_thread.join()

    except KeyboardInterrupt:
        print("Playback stopped by user.")
        print("Attempting graceful shutdown...")
        # make sure to turn off all notes

    if out is not None:
        for i in range(127):
            out.send(mido.Message('note_off', velocity=0, note=i, time=0))
        out.reset()
        out.close()
        print("Closed MIDI output.")

    print("Done")


if __name__ == "__main__":
    import argparse
    import mido
    import threading
    import time
    import os

    # args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list_ports",
        help="list available input and output MIDI ports and exit.",
        action="store_true",
    )
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "-c",
        "--control",
        help="the MIDI control signal number to use as human control.",
        type=int,
        default=10,
    )
    parser.add_argument(
        "-hi",
        "--human_impact",
        help="the percentage of human impact over the performance (0: only generated, 1: only human).",
        type=float,
        default=0,
    )
    parser.add_argument(
        "-i",
        "--input",
        help="the input MIDI port for the control signal.",
        type=int,
        default=None,
    )
    parser.add_argument(
        "-o",
        "--output",
        help="the output MIDI port for the performance.",
        type=int,
        default=None,
    )
    parser.add_argument(
        "-mc",
        "--midi-channel",
        help="the output MIDI channel for the performance.",
        type=int,
        default=1,
    )
    parser.add_argument(
        "-t",
        "--transpose",
        help="the number of semitones to transpose the tune of",
        type=int,
        default=0,
    )
    parser.add_argument(
        "-d",
        "--diatonic",
        help="whether or not error generation should be quantized to the tune's mode",
        action="store_true",
    )
    parser.add_argument(
        "-r",
        "--repeat",
        help="how many times the tune should be repeated",
        type=int,
        default=1,
    )
    parser.add_argument(
        "-bpm",
        help="the tempo of the performance. If None, defaults to the original file's tempo.",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--seed",
        help="Random seed for the performance.",
        type=int,
        default=42,
    )
    parser.add_argument(
        "--save",
        help="whether or not to export the performance. Playback will be disabled.",
        action="store_true",
    )
    parser.add_argument(
        "--no-prompt",
        help="whether or not to wait for user input before starting.",
        action="store_true",
    )
    parser.add_argument(
        "--output-dir",
        help="the output directory for generated performances. Defaults to the tune's directory.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--config",
        help="the path to a configuration file. Every option included in the configuration file will override command line arguments.",
        type=str,
        default=None,
    )
    args = parser.parse_args()

    main(args)
