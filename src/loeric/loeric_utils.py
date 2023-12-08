import mido

# how to approach a note from above or below in a major scale
above_approach_scale = [2, 1, 2, 1, 1, 2, 1, 2, 1, 2, 1, 1]
below_approach_scale = [-1, -1, -2, -1, -2, -1, -1, -2, -1, -2, -1, -2]

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
    input_number: int = None, output_number: int = None, list_ports: bool = False
):
    """
    Return the port names associated to the given indexes.
    If listing ports, only input and output port names will be printed.

    :param input_number: the input port index.
    :param output_number: the output port index.
    :param list_ports: whether or not to list port names and return.

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
    if input_number is None:
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
    if output_number is None:
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
