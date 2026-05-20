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

import logging
import random

import mido
import numpy as np

import loeric.element as le

logger = logging.getLogger(__name__)


class OutputInterface:

    @staticmethod
    def create_output(config: dict):

        if not config["active"]:
            return None
        if config["type"] == "midi":
            return MIDIOutput(
                port=config["port"],
                controls=config["controls"],
                send_cc=config["send_cc"],
                send_messages=config["send_messages"],
                velocity_range=config["velocity_range"],
                pitchbend_range=config["pitchbend_range"],
            )
        else:
            raise ValueError(f"Unknown output interface type {config["type"]}.")

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Send events to the output."""
        pass

    def reset(self):
        """Reset output state."""
        pass

    def set(self, contour_values: dict):
        """Set values to output."""
        pass


class MIDIQueue(le.Queue):
    """A priority queue of LOERICElements, by time."""

    def __init__(self):
        super().__init__()
        self._seq = 0
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
                self._seq,
                item,
            )
        )
        self._seq += 1

    def peek(self):
        return super().peek()[-1]

    def pop(self):
        return super().pop()[-1]


class MIDIOutput(OutputInterface):

    def __init__(
        self,
        port: str,
        controls: dict,
        send_cc: bool,
        send_messages: bool,
        velocity_range: list[int],
        pitchbend_range: int,
    ):

        self._out = mido.open_output(port)
        self._control_values = {}
        self._controls = controls
        self._send_cc = send_cc
        self._send_messages = send_messages
        self._velocity_range = velocity_range
        self._free_channels = {i: (-np.inf, -np.inf) for i in range(16)}
        self._pitchbend_range = pitchbend_range

        self._mpe_init()

        self._queue = MIDIQueue()

    def _mpe_init(self):
        for channel in range(16):
            self._out.send(
                mido.Message("control_change", channel=channel, control=101, value=0)
            )
            self._out.send(
                mido.Message("control_change", channel=channel, control=100, value=0)
            )
            self._out.send(
                mido.Message(
                    "control_change",
                    channel=channel,
                    control=6,
                    value=self._pitchbend_range,
                )
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

            min_v, max_v = self._velocity_range

            if event.duration == 0:
                return []

            overall_time = le.TimeDelta(eighth_duration=0)
            if absolute_time:
                overall_time = le.TimeDelta(eighth_duration=event._time.eighth_duration)

            messages = []

            bend_semitones = event._pitch - np.round(event._pitch)
            bend_percentage = bend_semitones / self._pitchbend_range

            event_velocity = event.velocity * (max_v - min_v) + min_v
            event_velocity = np.clip(event_velocity, min_v, max_v).astype(int)

            pb = min(8191, max(np.round(bend_percentage * 8191).astype(int), -8192))
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
                    note=np.round(event._pitch).astype(int),
                    time=overall_time.eighth_duration.astype(float),
                    channel=event.channel,
                    velocity=event_velocity,
                )
            )

            note_duration = le.TimeDelta(
                eighth_duration=event._duration.eighth_duration
            )
            if event._is_slide:

                previous_bend = bend_percentage
                resolution = 24

                for note in event._slide_targets:
                    slide_duration = le.TimeDelta(
                        eighth_duration=note.duration.eighth_duration / resolution
                    )

                    bend_semitones = note.pitch - event._pitch
                    bend_percentage = bend_semitones / self._pitchbend_range

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

            if event._duration == 0:
                note_duration += 0.001

            messages.append(
                mido.Message(
                    "pitchwheel",
                    pitch=0,
                    channel=event.channel,
                    time=(overall_time + note_duration).eighth_duration.astype(float),
                )
            )
            messages.append(
                mido.Message(
                    "note_off",
                    note=np.round(event._pitch).astype(int),
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
        logger.info("Reset and closed midi output.")

    def set(self, contour_values):
        self._control_values |= contour_values
        if not self._send_cc:
            return
        for c in self._controls:
            if c not in self._control_values:
                continue

            val = max(0, min(127, int(self._control_values[c] * 127)))

            logger.info(f"{c}: cc {self._controls[c]} {val}")
            message = mido.Message(
                "control_change", control=self._controls[c], channel=0, value=val
            )
            self._out.send(message)

    def _allocate_channel(self, event: le.LOERICElement):

        start_time = event.time
        end_time = event.time + event.duration

        for ch in self._free_channels:
            s, e = self._free_channels[ch]
            if start_time > e:
                self._free_channels[ch] = (start_time, end_time)
                return int(ch)

        # steal oldest voice
        ch = np.argmin([s for s, e in self._free_channels.values()])
        self._free_channels[ch] = (start_time, end_time)
        return ch

    def play_events(self, events: list[le.LOERICElement], tick):

        if not self._send_messages:
            return

        # obtain all midi messages
        for event in events:
            if isinstance(event, le.Note):
                channel = self._allocate_channel(event)
                event.channel = channel
            for e in self._event_to_midi(event, absolute_time=True):
                self._queue.push(e)

        while not self._queue.is_empty():

            m = self._queue.peek()

            if m.time <= tick:

                m = self._queue.pop()

                if not m.is_meta:

                    if m.type == "control_change":
                        if self._send_cc:
                            self._out.send(m)

                    elif m.type in ["note_on", "note_off", "pitchwheel"]:

                        if self._send_messages:
                            self._out.send(m)
            else:
                break
