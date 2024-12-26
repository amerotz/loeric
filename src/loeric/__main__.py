import argparse
import mido
import threading
import time
import os
import faulthandler

from collections.abc import Callable

from . import contour as cnt
from . import tune as tu
from . import groover as gr
from . import player as pl
from . import loeric_utils as lu


faulthandler.enable()
# bad code goes here

received_start = threading.Semaphore(value=0)
done_playing = threading.Event()
stopped = threading.Event()
playback_resumed = threading.Condition()


# play midi file
def play(
    groover: gr.Groover,
    tune: tu.Tune,
    out: mido.ports.BaseOutput,
    sync_port_out: mido.ports.BaseOutput,
    **kwargs,
) -> None:
    global received_start
    try:
        """
        Play the given tune with the given groover.

        :param groover: the groover object
        :param tune: the tune object
        :param kwargs: the performance arguments
        """
        # create player
        player = pl.Player(
            tempo=groover.tempo,
            key_signature=tune.key_signature,
            time_signature=tune.time_signature,
            save=kwargs["save"],
            verbose=kwargs["verbose"],
            midi_out=out,
        )

        # wait for start
        if kwargs["sync"]:
            received_start.acquire()

        # repeat as specified
        # iterate over messages
        while True:
            if stopped.is_set():
                with playback_resumed:
                    playback_resumed.wait()
            message = groover.next_event()
            if message is None:
                break

            if message.type == "sysex":
                print(f"Repetition {message.data[0]+1}/{kwargs['repeat']}")
                continue
            # perform notes
            elif lu.is_note(message):
                # make the groover play the messages
                new_messages = groover.perform(message)
            # keep meta messages intact
            else:
                if message.type == "songpos":
                    print(
                        "MAIN",
                        message.pos,
                        groover._note_index,
                        groover._contours["velocity"]._index,
                    )
                    if sync_port_out is not None:
                        sync_port_out.send(message)
                        print(f"Sent songpos {message.pos}")
                new_messages = [message]
            # play
            player.play(new_messages)

        # play an end note
        if not kwargs["no_end_note"]:
            player.play(groover.get_end_notes())

        if kwargs["save"]:
            name = os.path.splitext(os.path.basename(kwargs["source"]))[0]
            if kwargs["output_dir"] is None:
                dirname = os.path.dirname(kwargs["source"])
            else:
                if not os.path.isdir(kwargs["output_dir"]):
                    os.makedirs(kwargs["output_dir"])
                dirname = kwargs["output_dir"]

            filename = kwargs["filename"]
            if filename is None:
                filename = f"generated_{name}_{kwargs['seed']}.mid"
            player.save(f"{dirname}/{filename}")

        done_playing.set()
        print("Player thread terminated.")

    except Exception as e:
        # stop clock thread
        done_playing.set()
        print("Player thread terminated.")
        raise e


def clock_thread(groover: gr.Groover, sync_port_out: mido.ports.BaseOutput) -> None:
    """
    Dedicated thread to send real-time clock and song position messages.
    """
    # wait for start
    received_start.acquire()

    while not done_playing.is_set():
        sync_port_out.send(
            mido.Message(
                "clock",
                time=0,
            )
        )
        time.sleep((60 / groover.current_tempo) / 24)

    print("Clock thread terminated.")


def sync_thread(
    groover: gr.Groover, sync_port_in: mido.ports.BaseInput, out: mido.ports.BaseOutput
) -> None:
    """
    Handle MIDI start, clock, songpos and end messages.
    """
    global stopped
    while not done_playing.is_set():
        msg = sync_port_in.receive(block=True)
        if msg.type == "clock":
            groover.set_clock()
        elif msg.type == "reset":
            groover.reset_clock()
        elif msg.type == "songpos":
            print(f"Received JUMP {msg.pos}.")
            if stopped.is_set():
                out.reset()
                groover.jump_to_pos(msg.pos)
            else:
                print(f"Ignoring JUMP because playback is active.")
        elif msg.type == "start":
            received_start.release(n=2)
            print("Received START.")
        elif msg.type == "stop":
            stopped.set()
            print("Received STOP.")
        elif msg.type == "continue":
            out.reset()
            stopped = threading.Event()
            with playback_resumed:
                playback_resumed.notify_all()
            print("Received CONTINUE.")

    print("Sync thread terminated.")


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
        if lu.is_note(msg):
            pass
        for event_number in control2contour:
            if msg.is_cc(event_number):
                contour_name = control2contour[event_number]
                value = msg.value / 127
                groover.set_contour_value(contour_name, value)
                print(f"{contour_name}:\t{round(value, 2)}", end="\r")

    return callback


def main():
    global received_start, done_playing
    # args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--list_ports",
        help="list available input and output MIDI ports and exit.",
        action="store_true",
    )
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "-ic",
        "--intensity_control",
        help="the MIDI control signal number to use as intensity control.",
        type=int,
        default=10,
    )
    parser.add_argument(
        "-hic",
        "--human_impact_control",
        help="the MIDI control signal number to use as human impact control.",
        type=int,
        default=11,
    )
    parser.add_argument(
        "-hi",
        "--human_impact",
        help="the initial percentage of human impact over the performance (0: only generated, 1: only human).",
        type=float,
        default=0,
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
        "--sync",
        help="whether or not to wait for a MIDI start message.",
        action="store_true",
    )
    parser.add_argument(
        "--output-dir",
        help="the output directory for generated performances. Defaults to the tune's directory.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--filename",
        help="the output filename for the generated performance.",
        type=str,
        default=None,
    )
    dir_path = os.path.dirname(os.path.realpath(__file__))
    parser.add_argument(
        "--config",
        help="the path to a configuration file. Every option included in the configuration file will override command line arguments.",
        type=str,
        default=f"{dir_path}/loeric_config/loeric_config.json",
    )
    parser.add_argument(
        "--verbose",
        help="whether to write generated messages to terminal or not",
        action="store_true",
    )
    parser.add_argument(
        "--no-end-note",
        help="removes the generation of a final note at the end of all repetitions",
        action="store_true",
    )

    input_args = parser.add_mutually_exclusive_group()
    input_args.add_argument(
        "--create_in",
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
        "--create_out",
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
        "--create_sync",
        help="whether to create a new MIDI sync port or not",
        action="store_true",
    )
    sync_ports = sync_args.add_argument_group("sync ports")
    sync_ports.add_argument(
        "-si",
        "--sync_in",
        help="the sync input MIDI port for the performance.",
        type=int,
        default=None,
    )
    sync_ports.add_argument(
        "-so",
        "--sync_out",
        help="the sync output MIDI port for the performance.",
        type=int,
        default=None,
    )
    args = parser.parse_args()
    args = vars(args)

    # loeric instance id
    loeric_id = int(time.time())

    if args["create_in"]:
        port = mido.open_input(f"LOERIC in #{loeric_id}#", virtual=True)

    if args["create_out"]:
        out = mido.open_output(f"LOERIC out #{loeric_id}#", virtual=True)

    # sync port
    if args["sync"]:
        if args["create_sync"]:
            sync_port_in = mido.open_input(f"LOERIC SYNC #{loeric_id}#", virtual=True)
            sync_port_out = mido.open_output(f"LOERIC SYNC #{loeric_id}#", virtual=True)

    inport, outport = lu.get_ports(
        input_number=args["input"],
        output_number=args["output"],
        list_ports=args["list_ports"],
        create_in=args["create_in"],
        create_out=args["create_out"],
    )

    sync_inport, sync_outport = None, None
    if args["sync"]:
        sync_inport, sync_outport = lu.get_ports(
            input_number=args["sync_in"],
            output_number=args["sync_out"],
            list_ports=False,
            create_in=args["create_sync"],
            create_out=args["create_sync"],
        )

    if args["list_ports"]:
        return

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
    elif args["save"] or outport is None:
        out = None
    else:
        out = mido.open_output(outport)

    # open sync
    if args["create_sync"]:
        pass
    elif args["save"] or sync_inport is None or sync_outport is None:
        sync_port_in = None
        sync_port_out = None
    else:
        sync_port_in = mido.open_input(sync_inport)
        sync_port_out = mido.open_output(sync_outport)

    # consistency with MIDI spec and mido
    args["midi_channel"] -= 1

    if not args["sync"] and not args["no_prompt"] and not args["save"]:
        input("Press any key to start playback:")

    # start the player thread
    try:
        # load a tune
        tune = tu.Tune(args["source"], args["repeat"])

        # create groover
        groover = gr.Groover(
            tune,
            bpm=args["bpm"],
            midi_channel=args["midi_channel"],
            transpose=args["transpose"],
            diatonic_errors=args["diatonic"],
            random_weight=0.2,
            human_impact=args["human_impact"],
            seed=args["seed"],
            config_file=args["config"],
        )

        # set input callback
        if port is not None:
            port.callback = check_midi_control(
                groover,
                {
                    args["intensity_control"]: "intensity",
                    args["human_impact_control"]: "human_impact",
                },
            )

        if args["sync"]:
            print("\nWaiting for START message...")

        player_t = threading.Thread(
            target=play, args=(groover, tune, out, sync_port_out), kwargs=args
        )
        player_t.start()

        if args["sync"]:
            """
            clock_t = threading.Thread(
                target=clock_thread, args=(groover, sync_port_out)
            )
            clock_t.start()
            """

            sync_t = threading.Thread(
                target=sync_thread, args=(groover, sync_port_in, out)
            )
            sync_t.start()

        player_t.join()
        if args["sync"]:
            # clock_t.join()
            sync_t.join()

    except KeyboardInterrupt:
        print("\nPlayback stopped by user.")

    print("Closing midi ports...")

    # close midi input
    if port is not None:
        port.close()
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

    # close sync ports
    if args["sync"]:
        print("Closing sync ports...")
        sync_port_in.close()
        if sync_port_in.closed:
            print("Closed SYNC input.")
        sync_port_out.reset()
        sync_port_out.close()
        if sync_port_out.closed:
            print("Closed SYNC output.")
