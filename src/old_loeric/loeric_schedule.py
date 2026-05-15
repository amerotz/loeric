"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import argparse
import threading
import time

import mido
import pandas as pd

from . import groover as gr, loeric_utils as lu, player as pl, tune as tu


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
        help="the control change number to monitor to advance the schedule.",
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

    schedule = pd.read_csv(args["source"])

    tunes = []
    groovers = []
    for index, piece in schedule.iterrows():
        filename = piece["TUNE"]
        repeats = piece["REPEAT"]
        config = piece["CONFIG"]
        key = piece["KEY"]
        meter = piece["METER"]
        end_note = piece["DO END NOTE"]
        slow_start = piece["SLOW START"]
        slow_end = piece["SLOW END"]
        bpm = piece["BPM"]

        tune = tu.Tune(filename, repeats, key=key, meter=meter)
        groover = gr.Groover(
            tune,
            bpm=bpm,
            config_file=config,
            do_end_note=end_note,
            slow_start=slow_start,
            slow_end=slow_end,
            human_impact=1,
        )

        tunes.append(tune)
        groovers.append(groover)

    # create player
    player = pl.Player(tempo=groovers[0].current_tempo, midi_out=out)

    player_t = threading.Thread(target=player_loop, args=[player])

    print("Awaiting message...")
    player_t.start()

    play_tunes(player, tunes, groovers, port)

    try:

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


received_start = threading.Event()
current_groover = None


def get_callback(control):

    def check_skips(msg):

        if msg.type == "control_change" and msg.control != control:
            return
        if msg.value == 127:
            return

        if check_skips.counter == 0:
            received_start.set()
            print("received start")
            check_skips.counter += 1
        else:
            current_groover.skip_repetition = True
            print("Skipping at end of repetition.")

    check_skips.counter = 0

    return check_skips


def player_loop(player):

    received_start.wait()
    print("Player started")
    while True:

        player.play_next()


def play_tunes(player, tunes, groovers, port):
    global current_groover

    received_start.wait()
    print("Groovers started")

    for tune, groover in zip(tunes, groovers):

        current_groover = groover
        # set input callback
        if port is not None:
            port.callback = groover.check_midi_control()
        print("Playing next tune.")

        lu.play(
            groover,
            player,
            songpos_callback=None,
            repetition_callback=lambda x: print(x),
        )

        print("Player thread terminated.")
