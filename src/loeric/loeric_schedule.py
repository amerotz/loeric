import pandas as pd
import mido
import argparse
import time
import threading
from . import tune as tu
from . import groover as gr
from . import player as pl
from . import loeric_utils as lu


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="the schedule csv file.", nargs="?", default="")
    parser.add_argument(
        "-n",
        "--name",
        help="the name of this LOERIC instance.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "-c",
        "--control",
        help="the control change number to monitor.",
        type=int,
        default=66,
    )
    input_args = parser.add_mutually_exclusive_group()
    input_args.add_argument(
        "--create-in",
        help="whether to create a new MIDI input port or not",
        action="store_true",
    )
    input_args.add_argument(
        "-i",
        "--input",
        help="the input MIDI port for the performance.",
        type=int,
        default=None,
    )

    output_args = parser.add_mutually_exclusive_group()
    output_args.add_argument(
        "--create-out",
        help="whether to create a new MIDI output port or not",
        action="store_true",
    )
    output_args.add_argument(
        "-o",
        "--output",
        help="the output MIDI port for the performance.",
        type=int,
        default=None,
    )

    sync_args = parser.add_mutually_exclusive_group()
    sync_args.add_argument(
        "--create-sync",
        help="whether to create a new MIDI sync port or not",
        action="store_true",
    )
    sync_args.add_argument(
        "-s",
        "--sync",
        help="the sync MIDI port for the performance.",
        type=int,
        default=None,
    )

    args = parser.parse_args()
    args = vars(args)

    # loeric instance id
    if args["name"] is None:
        loeric_id = int(time.time())
    else:
        loeric_id = args["name"]

    if args["create_in"]:
        port = mido.open_input(f"LOERIC in #{loeric_id}#", virtual=True)

    if args["create_out"]:
        out = mido.open_output(f"LOERIC out #{loeric_id}#", virtual=True)

    if args["create_sync"]:
        scheduler_port = mido.open_input(f"LOERIC sync #{loeric_id}#", virtual=True)

    input_defined = args["input"] is not None or args["create_in"]
    output_defined = args["output"] is not None or args["create_out"]

    saving_defined = False

    inport, outport = lu.get_ports(
        input_number=args["input"],
        output_number=args["output"],
        list_ports=False,
        create_in=args["create_in"],
        create_out=args["create_out"],
        prompt_in=(not input_defined) and (not output_defined) and (not saving_defined),
        prompt_out=(not output_defined) and (input_defined or not saving_defined),
    )

    # open in
    if args["create_in"]:
        pass
    elif inport is not None:
        port = mido.open_input(inport)
    else:
        port = None

    # open out
    if args["create_out"]:
        pass
    elif outport is None:
        out = None
    else:
        out = mido.open_output(outport)

    # open sync
    if args["create_sync"]:
        pass
    else:
        scheduler_port = mido.open_input(mido.get_input_names()[args["sync"]])

    scheduler_port.callback = get_callback(args["control"])
    print("Awaiting message...")

    schedule = pd.read_csv(args["source"])

    tunes = []
    groovers = []
    for index, piece in schedule.iterrows():
        filename = piece["TUNE"]
        repeats = piece["REPEAT"]
        config = piece["CONFIG"]
        key = piece["KEY"]
        end_note = piece["DO END NOTE"]
        slow_start = piece["SLOW START"]
        slow_end = piece["SLOW END"]
        bpm = piece["BPM"]

        tune = tu.Tune(filename, repeats, key=key)
        groover = gr.Groover(
            tune,
            bpm=bpm,
            config_file=config,
            slow_start=slow_start,
            slow_end=slow_end,
            human_impact=1,
        )

        tunes.append(tune)
        groovers.append(groover)

    with received_start:
        received_start.wait()

    # create player
    player = pl.Player(tempo=groovers[0].current_tempo, midi_out=out)
    player.init_playback()

    player_t = threading.Thread(
        target=play_tunes,
        args=(player, tunes, groovers, port),
    )

    try:
        player_t.start()
        while player_t.is_alive():
            player_t.join(1)

    except KeyboardInterrupt:
        print("\nPlayback stopped by user.")

    # close midi input
    if port is not None:
        port.close()
        print("Closing midi ports...")
        if port.closed:
            print("Closed MIDI input.")

    # make sure to turn off all notes
    if out is not None:
        for i in range(127):
            out.send(mido.Message("note_off", velocity=0, note=i, time=0))
        out.reset()
        out.close()
        if out.closed:
            print("Closed MIDI output.")


received_start = threading.Condition()
skip_to_next = False


def get_callback(control):

    def check_skips(msg):
        global skip_to_next, received_start

        if msg.type == "control_change" and msg.control != control:
            return
        if msg.value == 127:
            return

        if check_skips.counter == 0:
            with received_start:
                received_start.notify()
            print("received start")
            check_skips.counter += 1
        else:
            skip_to_next = True
            print("Skipping at end of repetition.")

    check_skips.counter = 0

    return check_skips


def play_tunes(player, tunes, groovers, port):
    global skip_to_next, received_start

    for tune, groover in zip(tunes, groovers):

        # set input callback
        if port is not None:
            port.callback = groover.check_midi_control()

        # iterate over messages
        while True:

            message = groover.next_event()
            if message is None:
                break

            if message.type == "sysex":
                print(f"Repetition {message.data[0]+1}")
                groover._offset = 0
                groover._swing_offset = 0

                if skip_to_next:
                    skip_to_next = False
                    break

                continue

            # perform notes
            elif lu.is_note(message):
                # make the groover play the messages
                new_messages = groover.perform(message)
            # keep meta messages intact
            else:
                if message.type == "songpos":
                    pass
                new_messages = groover.perform(message)
            # play
            player.play(new_messages)

        # play an end note
        if groover.do_end_note:
            groover.reset_contours()
            groover.advance_contours()
            player.play(groover.get_end_notes())

    print("Player thread terminated.")
