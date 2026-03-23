import argparse
import faulthandler
import importlib.resources as ir
import os
import threading
import time

import mido

import loeric.groover as gr
import loeric.loeric_utils as lu
import loeric.player as pl
import loeric.tune as tu

from .server.server import start_server


faulthandler.enable()
# bad code goes here

play_event = threading.Event()
done_playing = threading.Event()


def player_loop(player, groover):

    play_event.wait()
    while not done_playing.is_set():

        while groover.stopped.is_set():
            player.reset()
            # print("player waiting play")
            groover.playback_resumed.wait()
            # print("player awake")
            player.init_playback()

        player.play_next()


def sync_thread(
    groover: gr.Groover,
    player: pl.Player,
    sync_port_in: mido.ports.BaseInput,
    out: mido.ports.BaseOutput,
) -> None:
    """
    Handle MIDI start, stop, songpos and tempo messages.
    """
    while not done_playing.is_set():
        msg = sync_port_in.receive(block=True)
        if msg.type == "sysex" and msg.data[0] == 69:
            tempo = sum(msg.data[1:])
            groover.set_tempo(tempo)
            print(f"Received SET TEMPO {tempo}.")
        elif msg.type == "reset":
            groover.reset_clock()
            print("Received RESET.")
        elif msg.type == "clock":
            groover.set_clock()
            print("Received CLOCK.")
        elif msg.type == "songpos":
            print(f"Received JUMP {msg.pos}.")
            if groover.stopped.is_set():
                if msg.pos > groover._tune.maximum_songpos:
                    print(
                        f"Ignoring JUMP because position {msg.pos} is greater than maximum position {groover._tune.maximum_songpos}."
                    )
                else:
                    groover.jump_to_pos(msg.pos)
                    player.set_song_time(groover._tune.position_time(msg.pos))
            else:
                print("Ignoring JUMP because playback is active.")
        elif msg.type == "start":
            play_event.set()
            print("Received START.")
        elif msg.type == "stop":
            groover.playback_resumed.clear()
            groover.stopped.set()
            print("Received STOP.")
        elif msg.type == "continue":
            groover.playback_resumed.set()
            groover.stopped.clear()
            print("Received CONTINUE.")

    print("Sync thread terminated.")


def main():
    # args
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server",
        help="Start local web server",
        action="store_true",
    )
    parser.add_argument(
        "--list-ports",
        help="list available input and output MIDI ports and exit.",
        action="store_true",
    )
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "-n",
        "--name",
        help="the name of this LOERIC instance.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "-ic",
        "--intensity-control",
        help="the MIDI control signal number to use as intensity control.",
        type=int,
        default=10,
    )
    parser.add_argument(
        "-hic",
        "--human-impact-control",
        help="the MIDI control signal number to use as human impact control.",
        type=int,
        default=11,
    )
    parser.add_argument(
        "-hi",
        "--human-impact",
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
        default=None,
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
    parser.add_argument(
        "--config",
        help="the path to a configuration file. Every option included in the configuration file will override command line arguments.",
        type=str,
        default=ir.files("loeric.loeric_config.performance").joinpath("config.json"),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        help="whether to write generated messages to terminal or not.\n 0: no output. 1: configuration and repetition. 2: configuration, repetition, ornaments. 3: configuration, repetition, contours. 4: configuration, repetition, intonation. 5: all output messages.",
        action="count",
        default=0,
    )
    parser.add_argument(
        "--do-end-note",
        help="plays a final note at the end of all repetitions",
        action="store_true",
    )
    parser.add_argument(
        "--slow-start",
        help="starts the performance at a slower tempo and gradually increases it.",
        action="store_true",
    )
    parser.add_argument(
        "--slow-end",
        help="ends the performance at a slower tempo.",
        action="store_true",
    )

    parser.add_argument(
        "--force-key",
        help="overrides any key information in the tune.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--force-meter",
        help="overrides any time signature information in the tune.",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--plot",
        help="plots the specified contour before playback.",
        nargs="+",
        type=str,
        default=None,
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
    sync_ports = sync_args.add_argument_group("sync ports")
    sync_ports.add_argument(
        "-si",
        "--sync-in",
        help="the sync input MIDI port for the performance.",
        type=int,
        default=None,
    )
    sync_ports.add_argument(
        "-so",
        "--sync-out",
        help="the sync output MIDI port for the performance.",
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

    if args["server"]:
        start_server()
        return

    if args["create_in"]:
        port = mido.open_input(f"LOERIC in #{loeric_id}#", virtual=True)

    if args["create_out"]:
        out = mido.open_output(f"LOERIC out #{loeric_id}#", virtual=True)

    # sync port
    if args["sync"]:
        if args["create_sync"]:
            sync_port_in = mido.open_input(f"LOERIC SYNC #{loeric_id}#", virtual=True)
            sync_port_out = mido.open_output(f"LOERIC SYNC #{loeric_id}#", virtual=True)

    input_defined = args["input"] is not None or args["create_in"]
    output_defined = args["output"] is not None or args["create_out"]

    saving_defined = args["save"]

    inport, outport = lu.get_ports(
        input_number=args["input"],
        output_number=args["output"],
        list_ports=args["list_ports"],
        create_in=args["create_in"],
        create_out=args["create_out"],
        prompt_in=(not input_defined) and (not output_defined) and (not saving_defined),
        prompt_out=(not output_defined) and (input_defined or not saving_defined),
    )

    sync_inport, sync_outport = None, None
    if args["sync"] and output_defined:
        sync_input_defined = (args["sync_in"] is not None) or args["create_sync"]
        sync_output_defined = (args["sync_out"] is not None) or args["create_sync"]
        sync_inport, sync_outport = lu.get_ports(
            input_number=args["sync_in"],
            output_number=args["sync_out"],
            list_ports=False,
            create_in=args["create_sync"],
            create_out=args["create_sync"],
            prompt_in=not sync_input_defined,
            prompt_out=not sync_output_defined,
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
    elif outport is None:
        out = None
    else:
        out = mido.open_output(outport)

    # open sync
    if args["create_sync"]:
        pass
    elif sync_inport is None or sync_outport is None:
        sync_port_in = None
        sync_port_out = None
    else:
        sync_port_in = mido.open_input(sync_inport)
        sync_port_out = mido.open_output(sync_outport)

    # consistency with MIDI spec and mido
    args["midi_channel"] -= 1

    # start the player thread
    try:
        # load a tune
        tune = tu.Tune(
            args["source"],
            args["repeat"],
            key=args["force_key"],
            meter=args["force_meter"],
            verbose=args["verbose"],
        )

        # check seed
        if args["seed"] is None:
            args["seed"] = int(time.time())

        # create groover
        groover = gr.Groover(
            tune,
            bpm=args["bpm"],
            midi_channel=args["midi_channel"],
            transpose=args["transpose"],
            human_impact=args["human_impact"],
            seed=args["seed"],
            config_file=args["config"],
            intensity_control=args["intensity_control"],
            human_impact_control=args["human_impact_control"],
            syncing=args["sync"],
            slow_start=args["slow_start"],
            slow_end=args["slow_end"],
            do_end_note=args["do_end_note"],
            verbose=args["verbose"],
            loeric_id=loeric_id,
        )

        if args["plot"] is not None:
            import matplotlib.pyplot as plt

            x = tune.float_times
            x /= max(x)
            plot_num = len(args["plot"])
            fig = plt.figure(figsize=(20, 5 * plot_num))
            axs = fig.subplots(plot_num, 1, sharex=True)
            if plot_num == 1:
                axs = [axs]
            for ax, contour in zip(axs, args["plot"]):
                ax.step(
                    x,
                    (
                        groover._contours["pitch_contour"]._contour
                        - min(groover._contours["pitch_contour"]._contour)
                    )
                    / (
                        max(groover._contours["pitch_contour"]._contour)
                        - min(groover._contours["pitch_contour"]._contour)
                    ),
                    linestyle=":",
                    where="post",
                )
                ax.step(
                    x, groover._contours[contour]._contour, where="post", marker="x"
                )
                ax.set_xlim(min(x) - 0.01, 1 + 0.01)
            plt.tight_layout()
            plt.show()

        # set input callback
        if port is not None:
            port.callback = groover.check_midi_control()

        # create player
        player = pl.Player(
            tempo=groover.tempo,
            key_signature=tune.key_signature,
            time_signature=tune.time_signature,
            save=args["save"],
            verbose=args["verbose"],
            midi_out=out,
            song_start_time=tune.times[0].eighth_duration,
        )

        player_t = threading.Thread(target=player_loop, args=[player, groover])
        player_t.start()

        if args["sync"]:

            sync_t = threading.Thread(
                target=sync_thread, args=(groover, player, sync_port_in, out)
            )
            sync_t.start()

        if (not args["sync"] and not args["no_prompt"]) and (
            input_defined or output_defined
        ):
            input("Press any key to start playback:")
            print()

        if args["sync"]:
            if args["verbose"] > 0:
                print("[INFO]\tWaiting for START message...")
            play_event.wait()
        else:
            play_event.set()

        def songpos_callback(message):
            if sync_port_out is not None:
                for msg in message.to_midi():
                    sync_port_out.send(msg)
                if args["verbose"] > 0:
                    print(
                        f"[INFO]\t{groover.loeric_id} SENT {message.position} ({time.time()})"
                    )

        # start playback
        try:
            lu.play(
                groover,
                player,
                songpos_callback=songpos_callback,
                repetition_callback=lambda x: print(x),
                **args,
            )

            if args["save"]:
                name = os.path.splitext(os.path.basename(args["source"]))[0]
                if args["output_dir"] is None:
                    dirname = os.path.dirname(args["source"])
                else:
                    if not os.path.isdir(args["output_dir"]):
                        os.makedirs(args["output_dir"])
                    dirname = args["output_dir"]

                filename = args["filename"]
                if filename is None:
                    filename = (
                        f"generated_{name}_{args['seed']}_{groover.loeric_id}.mid"
                    )
                if args["verbose"] > 0:
                    print(f"[INFO]\tSaving to {dirname}/{filename}.")
                player.save(f"{dirname}/{filename}")

        except Exception as e:
            raise e
        finally:
            # stop sync thread
            done_playing.set()
            if args["verbose"] > 0:
                print("[INFO]\tPlayer thread terminated.")

        while player_t.is_alive():
            player_t.join(1)

        if args["sync"]:
            while sync_t.is_alive():
                sync_t.join(1)

    except KeyboardInterrupt:
        if args["verbose"] > 0:
            print("[INFO]\tPlayback stopped by user.")

    # close midi input
    if port is not None:
        port.close()
        if args["verbose"] > 0:
            print("[INFO]\tClosing midi ports...")
        if port.closed:
            if args["verbose"] > 0:
                print("[INFO]\tClosed MIDI input.")

    # make sure to turn off all notes
    if out is not None:
        out.send(mido.Message("control_change", control=123, value=0))
        for j in range(16):
            for i in range(127):
                out.send(
                    mido.Message("note_off", velocity=0, note=i, channel=j, time=0)
                )
        out.reset()
        out.close()
        if out.closed:
            if args["verbose"] > 0:
                print("[INFO]\tClosed MIDI output.")

    # close sync ports
    if args["sync"]:
        if args["verbose"] > 0:
            print("[INFO]\tClosing sync ports...")
        sync_port_in.close()
        if sync_port_in.closed:
            if args["verbose"] > 0:
                print("[INFO]\tClosed SYNC input.")
        sync_port_out.reset()
        sync_port_out.close()
        if sync_port_out.closed:
            if args["verbose"] > 0:
                print("[INFO]\tClosed SYNC output.")
