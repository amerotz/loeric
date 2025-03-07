import mido
import numpy as np
import music21 as m21

# how to approach a note from above or below in a major scale
above_approach_scale = [2, 1, 2, 1, 1, 2, 1, 2, 1, 2, 1, 1]
below_approach_scale = [-1, -1, -2, -1, -2, -1, -1, -2, -1, -2, -1, -2]

# calculated as the shortest "possible" length of a note
# given the latest guinnes world record for
# most notes played in a minute on a piano
TRIGGER_DELTA = 0.05

MAX_TEMPO = 2**24 - 1


# key signatures
number_of_fifths = {
    "Cb": -7,
    "Abm": -7,
    "Gb": -6,
    "Ebm": -6,
    "Db": -5,
    "Bbm": -5,
    "Ab": -4,
    "Fm": -4,
    "Eb": -3,
    "Cm": -3,
    "Bb": -2,
    "Gm": -2,
    "F": -1,
    "Dm": -1,
    "C": 0,
    "Am": 0,
    "G": 1,
    "Em": 1,
    "D": 2,
    "Bm": 2,
    "A": 3,
    "F#m": 3,
    "E": 4,
    "C#m": 4,
    "B": 5,
    "G#m": 5,
    "F#": 6,
    "D#m": 6,
    "C#": 7,
    "A#m": 7,
}


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


'''
def is_contour_valid(msg: mido.Message) -> bool:
    """
    Check if a midi event is to be considered to calculate a contour.
    """
    return is_note_on(msg)
'''


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
    if input_number is None and not create_in:
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
    if output_number is None and not create_out:
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
