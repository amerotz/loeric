import time
import mido
import music21 as m21


class Player:
    """The class responsible for performance playback and saving."""

    def __init__(
        self,
        tempo: int,
        key_signature: str,
        time_signature: m21.meter.TimeSignature,
        save: bool,
        midi_out,
        verbose: bool = False,
    ):
        """
        Initialize the class.

        :param tempo: the performance's tempo in microseconds per quarter note.
        :param key_signature: the performance's key signature.
        :param time_signature: the performance's time signature.
        :param save: whether or not to save the performance to a midi file
        :param midi_out: the output midi port.
        """
        self._key_signature = key_signature
        self._time_signature = time_signature
        self._saving = save
        self._midi_out = midi_out
        self._tempo = tempo
        self._verbose = verbose

        if self._saving:
            self._midi_performance = mido.MidiFile(type=0)
            self._midi_track = mido.MidiTrack()
            self._midi_performance.ticks_per_beat = 32767
            self._midi_performance.tracks.append(self._midi_track)
            self._midi_track.append(mido.MetaMessage("set_tempo", tempo=self._tempo))
            self._midi_track.append(
                mido.MetaMessage("key_signature", key=key_signature)
            )
            self._midi_track.append(
                mido.MetaMessage(
                    "time_signature",
                    numerator=time_signature.numerator,
                    denominator=time_signature.denominator,
                )
            )

    def init_playback(self) -> None:
        """
        Initialize variables useful to keep track of playback time and avoid drifting.
        """

        # obtained from
        # mido/mido/midifiles/midifiles.py:423-424
        # to minimize drifting
        self._start_time = time.time()
        self._input_time = 0.0

    def play(self, messages: list[mido.Message]) -> None:
        """
        Play the messages in input and append them to the generated performance.
        If no midi port has been specified, the messages only be saved.

        :param messages: the midi messages to play.
        """

        for msg in messages:

            # obtained from
            # mido/mido/midifiles/midifiles.py:427-430
            self._input_time += msg.time
            playback_time = time.time() - self._start_time
            duration_to_next_event = self._input_time - playback_time

            if self._midi_out is not None:
                if not msg.is_meta:
                    # obtained from
                    # mido/mido/midifiles/midifiles.py:432-433
                    if duration_to_next_event > 0.0:
                        time.sleep(duration_to_next_event)
                    self._midi_out.send(msg)
                    if self._verbose:
                        print(msg)

            if self._saving:
                self._midi_track.append(msg)

    def reset(self) -> None:
        """
        Reset the output port.
        """
        if self._midi_out is not None:
            self._midi_out.reset()

    def save(self, filename: str) -> None:
        """
        Save the generated performance as a midi file.

        :param filename: the path to the output midi file.
        """
        for i, msg in enumerate(self._midi_performance.tracks[0]):
            self._midi_performance.tracks[0][i].time = round(
                mido.second2tick(
                    msg.time, self._midi_performance.ticks_per_beat, self._tempo
                )
            )
        self._midi_performance.save(filename)
