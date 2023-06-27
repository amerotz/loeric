import mido
import muspy as mp
import music21 as m21

from collections.abc import Callable


def is_note_on(msg: mido.Message) -> bool:
    """
    Check if a note event is to be considered a note-on event, that is:
    * its type is "note-on";
    * it has non-zero velocity.

    :param msg: the message to check.
    :return True if the message is a note on event.
    """
    return msg.type == "note_on" and msg.velocity != 0


class Tune:
    """A wrapper for a midi file."""

    def __init__(self, filename: str):
        """
        Initialize the class. A number of properties is computed:
        * the duration of the pickup bar, if there is any;
        * the key signature (only the first encountered is considered, key signature changes are not supported);
        * the time signature (only the first encountered is considered, time signature changes are not supported);

        :param filename: the path to the midi file.
        """
        mido_source = mido.MidiFile(filename)
        self._midi = list(mido_source)

        # retrieve duration of first bar
        m21_source = m21.converter.parse(filename)
        self._offset = list(m21_source.recurse().getElementsByClass("Measure"))[
            0
        ].duration.quarterLength

        # key signature
        msg = [m for m in self._midi if m.type == "key_signature"][0]
        self.key_signature = msg.key

        # time signature
        msg = [m for m in self._midi if m.type == "time_signature"][0]
        self._time_signature = m21.meter.TimeSignature()
        self._time_signature.numerator = msg.numerator
        self._time_signature.denominator = msg.denominator

        pass

    def filter(
        self, filtering_function: Callable[[mido.Message], bool]
    ) -> list[mido.Message]:
        """
        Retrieve the midi events that fullfill the given filtering function.

        :param filtering_function: the function filtering the midi events.
        :return: a list of midi events fullfilling the filtering function.
        """
        return [msg for msg in self._midi if filtering_function(msg)]
        pass

    def __len__(self) -> int:
        """
        Return the length of the list of midi messages.
        :return: the number of midi messages in this tune.
        """
        return len(self._midi)

    def __getitem__(self, idx: int) -> mido.Message:
        """
        Return the item in the midi event list corresponding to the given index.
        :param idx: the element index.
        :return: the midi message corresponding to that index.
        """
        return self._midi[idx]
