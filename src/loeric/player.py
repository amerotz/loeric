import time
import copy
import threading
import queue
import mido
import music21 as m21
import muspy as mp

from collections import defaultdict

from . import tune as tu


class Player:
    """The class responsible for performance playback and saving."""

    def __init__(
        self,
        tempo: int,
        key_signature=None,
        time_signature=None,
        save: bool = False,
        midi_out=None,
        verbose: int = 0,
        song_start_time=0,
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
        self._message_queue = []
        self.playback_done = threading.Condition()
        self.has_reached_wake_time = threading.Event()
        self._tempo_scale = 1
        self._time_division = tu.TimeDelta(
            eighth_duration=2 / tu.MINIMUM_QUARTER_DIVISION
        )

        self._song_time = tu.TimeDelta(eighth_duration=song_start_time)
        self._last_played_message_time = copy.deepcopy(self._song_time)
        self._notify_song_time = tu.TimeDelta(eighth_duration=1000000)

        if self._saving:
            self._midi_performance = mido.MidiFile(type=0)
            self._midi_track = mido.MidiTrack()
            self._midi_performance.ticks_per_beat = 32767
            self._midi_performance.tracks.append(self._midi_track)
            self._midi_track.append(mido.MetaMessage("set_tempo", tempo=self._tempo))
            """
            self._midi_track.append(
                mido.MetaMessage("key_signature", key=key_signature.root_str)
            )
            """
            if self._time_signature is not None:
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

    def set_tempo_scale(self, tempo_scale):
        self._tempo_scale = tempo_scale

    def add_notes(self, notes):
        midi_messages = tu.note_list_to_midi(notes)

        self.add_midi(midi_messages)

    def add_midi(self, messages):

        if len(messages) == 0:
            return
        self._message_queue.extend(messages)
        self._message_queue.sort(key=lambda x: (x.time, 1 if "off" in x.type else 1))

    def wake_me_up_at(self, time):
        self._notify_song_time = time
        self.has_reached_wake_time.clear()

    def play_next(self) -> None:
        """
        Play the messages in input and append them to the generated performance.
        If no midi port has been specified, the messages will only be saved.

        :param messages: the midi messages to play.
        """

        start_time = time.time()
        if self._song_time >= self._notify_song_time:
            self.has_reached_wake_time.set()
            with self.playback_done:
                self.playback_done.notify_all()

        while True:

            if len(self._message_queue) == 0:
                break

            delta = self._song_time - self._message_queue[0].time

            if delta < 0:
                break

            msg = self._message_queue.pop(0)
            if self._verbose == 5:
                print("[MIDI]\t", msg)
            msg.time = 0

            if msg.is_meta:
                continue

            if self._midi_out is not None:
                if msg.type != "songpos":
                    self._midi_out.send(msg)

            if self._saving:
                msg.time = (
                    self._song_time - self._last_played_message_time
                ).eighth_duration * self._tempo_scale
                self._midi_track.append(msg)

            self._last_played_message_time = copy.deepcopy(self._song_time)

        self._song_time += self._time_division
        if self._midi_out is not None:
            delay_time = time.time() - start_time
            time.sleep(
                max(
                    self._time_division.eighth_duration * self._tempo_scale
                    - delay_time,
                    0,
                )
            )

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
            print(
            self._midi_performance.tracks[0][i])
        self._midi_performance.save(filename)
