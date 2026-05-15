# This file is part of LOERIC.
#
# LOERIC is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# LOERIC is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with LOERIC. If not, see <https://www.gnu.org/licenses/>.

import random
import time

import element as le
import mido
import numpy as np


class MIDIQueue(le.Queue):
    """A priority queue of LOERICElements, by time."""

    def __init__(self):
        super().__init__()
        self._message_priority = {
            "pitchwheel": 0,
            "control_change": 1,
            "note_off": 2,
            "note_on": 3,
        }

    def push(self, item: mido.Message | mido.MetaMessage):
        priority = 999

        if item.type in self._message_priority:
            priority = self._message_priority[item.type]

        super().push(
            (
                item.time,
                priority,
                time.time(),
                item,
            )
        )

    def peek(self):
        return super().peek()[-1]

    def pop(self):
        return super().pop()[-1]


class MIDIPlayer:

    def __init__(self):
        self._out = mido.open_output(mido.get_output_names()[0])
        self._mpe_init()

        self._queue = MIDIQueue()
        self._current_channel = 0

    def _mpe_init(self):
        self._bend_down_semitones = 48
        self._bend_up_semitones = 48
        for channel in range(16):
            self._out.send(
                mido.Message("control_change", channel=channel, control=101, value=0)
            )
            self._out.send(
                mido.Message("control_change", channel=channel, control=100, value=0)
            )
            self._out.send(
                mido.Message("control_change", channel=channel, control=6, value=48)
            )
            self._out.send(
                mido.Message("control_change", channel=channel, control=38, value=0)
            )

    def _event_to_midi(self, event, absolute_time=False):

        time = event.duration
        if absolute_time:
            time += event.time

        if isinstance(event, le.SongPosition):
            return [
                mido.Message("songpos", pos=event.position, time=time.eighth_duration)
            ]

        elif isinstance(event, le.KeySignature):
            return [
                mido.MetaMessage(
                    "key_signature",
                    key=le.NOTE_NAMES[event.major_root],
                    time=time.eighth_duration,
                )
            ]

        elif isinstance(event, le.Note):

            if event.duration == 0:
                return []

            overall_time = le.TimeDelta(eighth_duration=0)
            if absolute_time:
                overall_time = le.TimeDelta(eighth_duration=event.time.eighth_duration)

            messages = []

            bend_semitones = event.pitch - np.round(event.pitch)
            if bend_semitones > 0:
                bend_percentage = bend_semitones / self._bend_up_semitones
            else:
                bend_percentage = bend_semitones / self._bend_down_semitones

            pitch = max(0, min(127, np.round(event.pitch).astype(int)))

            pb = int(np.clip(np.round(bend_percentage * 8191), -8192, 8191))
            messages.append(
                mido.Message(
                    "pitchwheel",
                    pitch=pb,
                    channel=event.channel,
                    time=overall_time.eighth_duration,
                )
            )
            messages.append(
                mido.Message(
                    "note_on",
                    note=pitch,
                    time=overall_time.eighth_duration,
                    channel=event.channel,
                    velocity=max(0, min(127, int(127 * event.velocity))),
                )
            )

            note_duration = le.TimeDelta(eighth_duration=event.duration.eighth_duration)
            if event.is_slide:

                previous_bend = bend_percentage
                resolution = 24

                for note in event.slide_targets:
                    slide_duration = le.TimeDelta(
                        eighth_duration=note.duration.eighth_duration / resolution
                    )

                    bend_semitones = note.pitch - event.pitch
                    if bend_semitones > 0:
                        bend_percentage = bend_semitones / self._bend_up_semitones
                    else:
                        bend_percentage = bend_semitones / self._bend_down_semitones

                    # append messages
                    mult = random.uniform(0.25, 0.5)
                    for j in range(resolution):

                        overall_time = overall_time + slide_duration

                        perc = j / resolution
                        perc **= mult
                        pb = (1 - perc) * previous_bend + perc * bend_percentage
                        pb = min(8191, max(np.round(pb * 8191).astype(int), -8192))
                        messages.append(
                            mido.Message(
                                "pitchwheel",
                                pitch=pb,
                                channel=event.channel,
                                time=float(overall_time.eighth_duration),
                            )
                        )
                        note_duration = note_duration - slide_duration

                    previous_bend = bend_percentage

            if event.duration == 0:
                note_duration += 0.001

            messages.append(
                mido.Message(
                    "note_off",
                    note=pitch,
                    channel=event.channel,
                    time=(overall_time + note_duration).eighth_duration.astype(float),
                    velocity=0,
                )
            )

            return messages

        return []

    def reset(self):
        self._out.reset()
        self._out.close()

    def _play_events(self, events: list[le.LOERICElement], tick):

        # obtain all midi messages
        for event in events:
            event.channel = self._current_channel
            self._current_channel += 1
            self._current_channel %= 16
            for e in self._event_to_midi(event, absolute_time=True):
                self._queue.push(e)

        while not self._queue.is_empty():
            m = self._queue.peek()
            if m.time <= tick:
                m = self._queue.pop()
                if not m.is_meta:
                    # mpe
                    self._out.send(m)
            else:
                break
