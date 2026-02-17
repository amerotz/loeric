import importlib.resources as ir
import pathlib
import sys
import time

import mido
import numpy as np

from . import tune as tu


# how to approach a note from above or below in a major scale
above_approach_scale = [2, 1, 2, 1, 1, 2, 1, 2, 1, 2, 1, 1]
below_approach_scale = [-1, -1, -2, -1, -2, -1, -1, -2, -1, -2, -1, -2]

# calculated as the shortest "possible" length of a note
# given the latest guinnes world record for
# most notes played in a minute on a piano
TRIGGER_DELTA = 0.05

MAX_TEMPO = 2**24 - 1

# to handle builds
if hasattr(sys, "_MEIPASS"):
    general_configs_path = pathlib.Path(sys._MEIPASS) / "loeric"
else:
    general_configs_path = pathlib.Path(__file__).parent

general_configs_path = general_configs_path / "loeric_config" / "performance"
# general_configs_path = ir.files("loeric.loeric_config.performance")

# key signatures
number_of_fifths = [0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5]


def midi_to_freq(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def freq_to_midi(freq):
    return 69 + 12 * np.log2(freq / 440)


# play midi file
def play(
    groover,
    player,
    loop_condition=lambda: True,
    note_callback=None,
    songpos_callback=None,
    repetition_callback=None,
    **kwargs,
) -> None:
    """
    Play the given tune with the given groover.

    :param groover: the groover object
    :param player: the player object
    :param loop_condition: a function evaluating when to stop
    :param note_callback: callback on a note message
    :param songpos_callback: callback on a song position message
    :param repetition_callback: callback on a repetition message
    :param kwargs: the performance arguments
    """

    player.init_playback()
    player.reset_song_time(
        song_time=groover._tune.times[0].eighth_duration,
    )

    average_loop_time = 0
    iterations = 0
    next_event_time = 0

    # iterate over messages
    while loop_condition():

        iterations += 1

        if groover.stopped.is_set():
            while groover.stopped.is_set():
                groover.playback_resumed.wait()

        # start measuring loop
        loop_start_time = time.time()
        original_message = groover.next_event()

        if original_message is None:
            player.wake_me_up_at(next_event_time)
            groover.reset()
            break

        new_messages = []
        # perform notes
        if original_message.is_note:
            # make the groover play the messages
            midi_headers, new_messages = groover.perform(original_message)
            if note_callback is not None:
                note_callback(original_message)
        # keep meta messages intact
        else:
            if isinstance(original_message, tu.SongPosition):
                if songpos_callback is not None:
                    songpos_callback(original_message)
            elif isinstance(original_message, tu.Repetition):
                if repetition_callback is not None:
                    repetition_callback(original_message)
                if groover.skip_repetition:
                    break
            elif isinstance(original_message, tu.KeySignature):
                if groover._tune.forced_key:
                    if kwargs["verbose"] > 0:
                        print(
                            f"[INFO]\tIgnoring key change (forced key). {original_message}"
                        )
                else:
                    if kwargs["verbose"] > 0:
                        print(f"[INFO]\tChanging key. {original_message}")
                    groover._tune.set_key_signature(original_message)
            elif isinstance(original_message, tu.Chord):
                if kwargs["verbose"] > 0:
                    if original_message.is_user:
                        print(f"[INFO]\tForcing chord: {original_message}")
                    else:
                        print(f"[INFO]\tPlaying chord: {original_message}")
                groover._tune.set_chord(original_message)
            else:
                if kwargs["verbose"] > 0:
                    print(
                        f"\033[38;2;255;255;0m[WARN]\tUnknown message type {type(original_message)}.\033[0m"
                    )

            midi_headers = original_message.to_midi(absolute_time=True)

        player.set_tempo_scale(groover.tempo_scale)
        player.add_notes(new_messages)
        player.add_midi(midi_headers)

        # stop measuring loop
        loop_end_time = time.time()
        loop_duration = loop_end_time - loop_start_time
        average_loop_time *= 0.2
        average_loop_time += 0.8 * loop_duration

        message_duration_seconds = (
            original_message.duration.eighth_duration * groover._eighth_duration_seconds
        )

        # calculate time to wake up for next message
        next_event_time = original_message.time + original_message.duration
        time_to_think = next_event_time - 2 * (
            average_loop_time / groover._eighth_duration_seconds
        )

        if iterations == 0:
            player.wake_me_up_at(next_event_time)

        if (
            average_loop_time > message_duration_seconds
            and original_message.duration != 0
        ):
            if kwargs["verbose"]:
                print(
                    f"\033[38;2;255;255;0m[WARN] Intra-note computations are taking too much time ({np.round(average_loop_time, 3)} vs {np.round(message_duration_seconds, 3)}). Free your CPU!\033[0m"
                )

        # wake up slightly before next note
        player.wake_me_up_at(time_to_think)
        player.has_reached_wake_time.wait()

    if groover.do_end_note:
        groover.reset()
        groover.advance_contours()
        end_notes = groover.get_end_notes()
        player.add_notes(end_notes)

        player.wake_me_up_at(end_notes[-1].time + end_notes[-1].duration)
    else:
        player.wake_me_up_at(groover.performance_time)

    player.has_reached_wake_time.wait()


# 0 = major
# 1 = minor
# 2 = diminished
# 3 = augmented
# ####################### C C#  D Eb  E  F F#  G G#  A A#  B
chord_quality = np.array([0, 2, 1, 2, 1, 0, 2, 0, 2, 1, 0, 2])


# pitches that need quantization to major scale (then shifted according to modes)
needs_pitch_quantization = [
    False,  # C
    True,  # C#
    False,  # D
    True,  # D#
    False,  # E
    False,  # F
    True,  # F#
    False,  # G
    True,  # G#
    False,  # A
    True,  # A#
    False,  # B
]


def is_note_on(msg: mido.Message) -> bool:
    """
    Check if a midi event is to be considered a note-on event, that is:

    * its type is "note-on";
    * it has non-zero velocity.

    :param msg: the message to check.

    :return: True if the message is a note on event.
    """
    return msg.type == "note_on" and msg.velocity != 0


def is_note_off(msg: mido.Message) -> bool:
    """
    Check if a midi event is to be considered a note-off event, that is:

    * its type is "note-off" or
    * its type is "note-on" and it has 0 velocity.

    :param msg: the message to check.

    :return: True if the message is a note on event.
    """
    return msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0)


def is_note(msg: mido.Message) -> bool:
    """
    Check if a midi event is a note event (either note-on or note-off).

    :param msg: the message to check.

    :return: True if the message is a note event.
    """
    return "note" in msg.type


def get_ports(
    input_number: int = None,
    output_number: int = None,
    list_ports: bool = False,
    create_in: bool = False,
    create_out: bool = False,
    prompt_in: bool = False,
    prompt_out: bool = False,
):
    """
    Return the port names associated to the given indexes.
    If listing ports, only input and output port names will be printed.

    :param input_number: the input port index.
    :param output_number: the output port index.
    :param list_ports: whether or not to list port names and return.
    :param create_in: whether or not a new input will be created.
    :param create_out: whether or not a new output will be created.

    :return: a tuple (input, output) containing the input and output port names.
    """

    inport = None
    outport = None

    # list ports
    if list_ports:
        print("Available inputs:")
        for i, p in enumerate(mido.get_input_names()):
            print(f"{i}:\t{p}")
        print()
        print("Available outputs:")
        for i, p in enumerate(mido.get_output_names()):
            print(f"{i}:\t{p}")
        return inport, outport

    # if no input is defined
    if prompt_in:
        names = mido.get_input_names()
        if len(names) == 0:
            print("No input port available.")
            in_index = None
        else:
            print()
            for i, m in enumerate(names):
                print(f"{i} : {m}")
            in_index = int(input("Choose input midi port:"))
            print()
    else:
        in_index = input_number

    # if no output is defined
    if prompt_out:
        names = mido.get_output_names()
        if len(names) == 0:
            print("No output port available.")
            out_index = None
        else:
            for i, m in enumerate(names):
                print(f"{i} : {m}")
            out_index = int(input("Choose output midi port:"))
    else:
        out_index = output_number

    # get the ports
    if in_index is not None:
        inport = mido.get_input_names()[in_index]
    if out_index is not None:
        outport = mido.get_output_names()[out_index]

    return inport, outport
