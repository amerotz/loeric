import mido
import muspy as mp
import music21 as m21

from collections.abc import Callable


def is_note_on(msg: mido.Message) -> bool:
    """
    Check if a midi event is to be considered a note-on event, that is:
    * its type is "note-on";
    * it has non-zero velocity.

    :param msg: the message to check.

    :return: True if the message is a note on event.
    """
    return msg.type == "note_on" and msg.velocity != 0


def is_note(msg: mido.Message) -> bool:
    """
    Check if a midi event is a note event (either note-on or note-off).

    :param msg: the message to check.

    :return: True if the message is a note event.
    """
    return "note" in msg.type


class Tune:
    """A wrapper for a midi file."""

    def __init__(self, filename: str) -> None:
        """
        Initialize the class. A number of properties is computed:

        * the duration of the pickup bar, if there is any;
        * the key signature (only the first encountered is considered, key signature changes are not supported);
        * the time signature (only the first encountered is considered, time signature changes are not supported);

        :param filename: the path to the midi file.

        """
        mido_source = mido.MidiFile(filename)

        self._filename = filename
        self._midi = list(mido_source)

        # key signature
        self._key_signature = self.get_key_signature()

        # time signature
        self._time_signature = self.get_time_signature()

        # tempo in microseconds per quarter
        self._tempo = self.get_original_tempo()

        # pickup bar
        self.offset = self.get_performance_offset()

        # number of quarter notes per bar
        quarters_per_bar = (
            4 * self._time_signature.numerator / self._time_signature.denominator
        )
        # bar and beat duration in seconds
        self.bar_duration = quarters_per_bar * self._quarter_duration
        self.beat_duration = self.bar_duration / self._time_signature.beatCount

    @property
    def _quarter_duration(self) -> float:
        """
        Return the duration of a quarter note in seconds given the current tempo.

        :return: the amount of seconds corresponding to a quarter note given the current tempo.
        """
        return self._tempo / 1e6

    def get_performance_offset(self) -> float:
        """
        Return the length of the pickup bar, if there is any.

        :return: the length of the pickup bar in seconds.
        """
        # retrieve duration of first bar
        m21_source = m21.converter.parse(self._filename)

        # performance offset in seconds
        offset = list(m21_source.recurse().getElementsByClass("Measure"))[
            0
        ].duration.quarterLength

        offset *= self._quarter_duration
        return offset

    def get_original_tempo(self) -> int:
        """
        Retrieve the tempo of the tune, if there is any.
        Only the first tempo change will be retrieved.

        :return: the first tempo change if there is any, else None.
        """
        msg = self.filter(lambda x: x.type == "set_tempo")
        if len(msg) == 0:
            return None
        return msg[0].tempo

    def get_time_signature(self) -> m21.meter.TimeSignature:
        """
        Retrieve the time signature of the tune, if there is any.
        Only the first time signature will be retrieved.

        :return: the first time signature if there is any, else None.
        """

        # msg = [m for m in self._midi if m.type == "time_signature"][0]
        msg = self.filter(lambda x: x.type == "time_signature")
        if len(msg) == 0:
            return None
        time_signature = m21.meter.TimeSignature()
        time_signature.numerator = msg[0].numerator
        time_signature.denominator = msg[0].denominator
        return time_signature

    def get_key_signature(self) -> str:
        """
        Retrieve the key signature of the tune, if there is any.
        Only the first key signature will be retrieved.

        :return: the first key signature if there is any, else None.
        """

        # msg = [m for m in self._midi if m.type == "key_signature"]
        msg = self.filter(lambda x: x.type == "key_signature")
        if len(msg) == 0:
            return None
        return msg[0].key

    def filter(
        self, filtering_function: Callable[[mido.Message], bool]
    ) -> list[mido.Message]:
        """
        Retrieve the midi events that fullfill the given filtering function.

        :param filtering_function: the function filtering the midi events.

        :return: a list of midi events fullfilling the filtering function.
        """
        return [msg for msg in self._midi if filtering_function(msg)]

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
