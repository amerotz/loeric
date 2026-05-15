"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import copy
import threading
import time

import mido
import numpy as np

import loeric.loeric_utils as lu
import loeric.tune as tu


class Player:
    """The class responsible for performance playback and saving."""

    def __init__(
        self,
        tempo: int,
        key_signature=None,
        time_signature=None,
        save: bool = False,
        midi_out=None,
        midi_sync_out=None,
        verbose: int = 0,
        song_start_time=0,
        midi_out_lock=None,
        midi_sync_out_lock=None,
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
        self._midi_sync_out = midi_sync_out

        self._tempo = tempo
        self._verbose = verbose
        self._message_queue = []
        self._message_queue_lock = threading.Lock()
        self._active_notes = []
        self.has_reached_wake_time = threading.Event()

        if midi_out_lock is None:
            self._midi_out_lock = threading.Lock()
        else:
            self._midi_out_lock = midi_out_lock
        print(id(self._midi_out_lock))

        if midi_sync_out_lock is None:
            self._midi_sync_out_lock = threading.Lock()
        else:
            self._midi_sync_out_lock = midi_sync_out_lock

        self._tempo_scale = 1
        self._time_division = tu.TimeDelta(
            eighth_duration=2 / tu.MINIMUM_QUARTER_DIVISION
        )

        self.__song_start_time = song_start_time
        self._song_time = tu.TimeDelta(eighth_duration=song_start_time)
        self._last_played_message_time = self._song_time.eighth_duration
        self._notify_song_time = tu.TimeDelta(eighth_duration=song_start_time)

        if self._saving:
            self._midi_performance = mido.MidiFile(type=0)
            self._midi_track = mido.MidiTrack()
            self._midi_performance.ticks_per_beat = 32767
            self._midi_performance.tracks.append(self._midi_track)
            self._midi_track.append(
                mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(self._tempo.qpm))
            )
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

    def set_midi_out(self, midi_out):
        with self._midi_out_lock:
            self._midi_out = midi_out

    def init_playback(self) -> None:
        """
        Initialize variables useful to keep track of playback time and avoid drifting.
        """

        # obtained from
        # mido/mido/midifiles/midifiles.py:423-424
        # to minimize drifting
        # self._start_time = time.time()
        # self._input_time = 0.0

    def reset_song_time(self, song_time=None):
        if song_time is None:
            self._song_time = tu.TimeDelta(eighth_duration=self.__song_start_time)
        else:
            self._song_time = tu.TimeDelta(eighth_duration=song_time)

    def set_tempo_scale(self, tempo_scale):
        self._tempo_scale = tempo_scale

    def add_notes(self, notes):
        midi_messages = tu.note_list_to_midi(notes)

        self.add_midi(midi_messages)

    def _message_priority(self, message):

        add_time = time.time()
        message_priority = ["pitchwheel", "note_off", "note_on", "control_change"]
        # first time
        m_time = message.time

        # then pitch (if there)
        pitch = -1
        if "note" in message.type:
            pitch = message.note

        if message.type in message_priority:
            kind = message_priority.index(message.type)
        else:
            kind = len(message_priority)

        return (m_time, kind, pitch, add_time)

    def add_midi(self, messages):

        if len(messages) == 0:
            return
        with self._message_queue_lock:
            self._message_queue.extend(messages)
            self._message_queue.sort(key=lambda x: self._message_priority(x))

    def wake_me_up_at(self, time):
        self._notify_song_time = time

    def set_song_time(self, value):
        if value is None:
            return
        self._song_time = tu.TimeDelta(eighth_duration=value)
        self._notify_song_time = tu.TimeDelta(eighth_duration=value)

        # remove any messages
        with self._message_queue_lock:
            self._message_queue = []

    def play_next(self) -> None:
        """
        Play the messages in input and append them to the generated performance.
        If no midi port has been specified, the messages will only be saved.

        :param messages: the midi messages to play.
        """

        # wake up the groover if time reached
        if self._song_time >= self._notify_song_time:
            self.has_reached_wake_time.set()

        # store start time of loop
        start_time = time.time()
        # until we have stuff to play

        while True:

            # check the queue
            with self._message_queue_lock:
                if len(self._message_queue) == 0:
                    break

                # if we have not reached the next message in the queue, stop
                if self._song_time < self._message_queue[0].time:
                    break

                # else get the message
                msg = self._message_queue.pop(0)

            # save midi performance
            if self._saving:

                # TODO
                # fix export
                save_message = copy.deepcopy(msg)
                # change time to ticks
                new_time = np.round(save_message.time * 32767 / 2).astype(int)
                save_message.time = new_time
                print(save_message)
                # add to track
                self._midi_track.append(save_message)

            # meta messages can't be performed
            if msg.is_meta:
                continue

            # avoid sending double note on messages
            # by turning off already sounding notes
            if lu.is_note_on(msg):
                key = f"{msg.note}_{msg.channel}"

                # if note is active on that channel
                # and we need to play it again
                if key in self._active_notes:

                    # turn off existing note
                    # before the other one is sent
                    off_msg = mido.Message(
                        "note_off", note=msg.note, channel=msg.channel, velocity=0
                    )

                    if self._verbose == 5:
                        print("[MIDI]\t", off_msg)

                    self._midi_out.send(off_msg)

                    # no need to remove it from active notes since
                    # it will be sent again

                else:
                    # register that this note is active
                    self._active_notes.append(f"{msg.note}_{msg.channel}")

            elif lu.is_note_off(msg):
                # if it was active
                key = f"{msg.note}_{msg.channel}"

                # remove it from active notes
                if key in self._active_notes:
                    self._active_notes.remove(key)

            if self._verbose == 5:
                print("[MIDI]\t", msg)

            # instant
            msg.time = 0

            # if we have a sync port, send songpos messages there
            if msg.type == "songpos" and self._midi_sync_out is not None:
                with self._midi_sync_out_lock:
                    self._midi_sync_out.send(msg)

            # if there is a midi output (so we are not saving)
            # send the message there
            elif self._midi_out is not None:

                with self._midi_out_lock:
                    self._midi_out.send(msg)

        # advance song performance time by small delta
        self._song_time += self._time_division

        # if we are not saving
        if self._midi_out is not None:

            # fraction of eight note converted to seconds
            wait_time = self._time_division.eighth_duration * self._tempo_scale

            # compensate loop duration
            delay_time = time.time() - start_time
            wait_time -= delay_time

            # cannot wait negative time
            time.sleep(max(wait_time, 0))

    def reset(self) -> None:
        """
        Explicitly reset the output port.
        """
        if self._midi_out is not None:
            with self._midi_out_lock:
                for item in self._active_notes:

                    note, channel = item.split("_")
                    print(note, channel)
                    self._midi_out.send(
                        mido.Message(
                            "note_off", note=int(note), channel=int(channel), velocity=0
                        )
                    )

    def save(self, filename: str) -> None:
        """
        Save the generated performance as a midi file.

        :param filename: the path to the output midi file.
        """
        self._midi_track.sort(key=lambda x: x.time)
        print(self._midi_track)
        prev_time = self._midi_track[0].time
        for i in range(len(self._midi_track)):
            new_time = self._midi_track[i].time - prev_time
            prev_time = self._midi_track[i].time
            self._midi_track[i].time = new_time

        self._midi_performance.save(filename)
