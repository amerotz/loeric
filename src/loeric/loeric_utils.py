import mido
import muspy as mp
import numpy as np
import music21 as m21

from . import tune as tu


# how to approach a note from above or below in a major scale
above_approach_scale = [2, 1, 2, 1, 1, 2, 1, 2, 1, 2, 1, 1]
below_approach_scale = [-1, -1, -2, -1, -2, -1, -1, -2, -1, -2, -1, -2]

# calculated as the shortest "possible" length of a note
# given the latest guinnes world record for
# most notes played in a minute on a piano
TRIGGER_DELTA = 0.05

MAX_TEMPO = 2**24 - 1


# key signatures
number_of_fifths = [0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5]


# play midi file
def play(
    groover,
    player,
    songpos_callback=None,
    repetition_callback=None,
    **kwargs,
) -> None:
    """
    Play the given tune with the given groover.

    :param groover: the groover object
    :param kwargs: the performance arguments
    """

    player.init_playback()
    player.reset_song_time(
        song_time=groover._tune.times[0].eighth_duration,
    )

    # iterate over messages
    while True:

        if groover.stopped.is_set():
            while groover.stopped.is_set():
                groover.playback_resumed.wait()

        original_message = groover.next_event()

        if original_message is None:
            groover.reset()
            break

        new_messages = []
        # perform notes
        if original_message.is_note:
            # make the groover play the messages
            midi_headers, new_messages = groover.perform(original_message)
        # keep meta messages intact
        else:
            if isinstance(original_message, tu.SongPosition):
                songpos_callback(original_message)
            elif isinstance(original_message, tu.Repetition):
                repetition_callback(original_message)
            elif (
                isinstance(original_message, tu.KeySignature)
                and not groover._tune.forced_key
            ):
                if kwargs["verbose"] > 0:
                    print(f"[INFO]\tChanging key. {original_message}")
                groover._tune.set_key_signature(original_message)
            midi_headers = original_message.to_midi(absolute_time=True)

        player.set_tempo_scale(groover.tempo_scale)
        player.add_midi(midi_headers)
        player.add_notes(new_messages)

        player.wake_me_up_at(original_message.time + original_message.duration)

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


def get_root(key_signature: str) -> int:
    """
    Return the tonic of a given key signature.

    :param key_signature: the key signature in the following format: [A-G](#|b)?m?
    :return: the toinc of the key signature.
    """

    base = int(m21.pitch.Pitch(key_signature[0]).ps)

    if "b" in key_signature:
        base -= 1
    elif "#" in key_signature:
        base += 1

    base += 12
    base %= 12

    return base


def major_root(root, mode) -> int:
    """
    :return: the root of the relative major of the key signature in pitch space.
    """
    mode_offset = {
        "major": 0,
        "minor": 3,
        "dorian": 10,
        "mixolydian": 5,
    }
    return (root + mode_offset[mode]) % 12


# 0 = major
# 1 = minor
# 2 = diminished
# 3 = augmented
##########################C C#  D Eb  E  F F#  G G#  A A#  B
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


def get_chord_pitches(harmony: int) -> np.array:
    """
    Return the pitches of a major or minor chord in semitones from the root.

    :param harmony: the chord. Values 0-11 indicate a major chord. Values 12-23 indicate a minor chord. Values 24-35 indicate a diminished chord. Values 36-48 indicate an augmented chord.

    :return: the pitches that are part of the input chord.
    """
    third = 4
    fifth = 7

    chord_quality = int(harmony / 12)
    if chord_quality == 1:
        third = 3
    elif chord_quality == 2:
        third = 3
        fifth = 6
    elif chord_quality == 3:
        fifth = 8

    return np.array([0, third, fifth])


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
