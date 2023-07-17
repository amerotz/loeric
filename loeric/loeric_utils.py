import mido


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
    # list ports
    if list_ports:
        print("Available inputs:")
        for i, p in enumerate(mido.get_input_names()):
            print(f"{i}:\t{p}")
        print()
        print("Available outputs:")
        for i, p in enumerate(mido.get_output_names()):
            print(f"{i}:\t{p}")
        return None, None

    # if no input is defined
    if input_number is None:
        print()
        for i, m in enumerate(mido.get_input_names()):
            print(f"{i} : {m}")
        in_index = int(input("Choose input midi port:"))
        print()
    else:
        in_index = input_number

    # if no output is defined
    if output_number is None:
        for i, m in enumerate(mido.get_output_names()):
            print(f"{i} : {m}")
        out_index = int(input("Choose output midi port:"))
    else:
        out_index = output_number

    # get the ports
    inport = mido.get_input_names()[in_index]
    outport = mido.get_output_names()[out_index]

    return inport, outport
