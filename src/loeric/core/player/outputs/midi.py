import logging
import random
import threading

import mido
import numpy as np
import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.outputs.base as lob

logger = logging.getLogger(__name__)


class MIDIQueue(le.Queue):
    """A priority queue of MIDI messages ordered by time, then by message type.

    Message type priority (lowest first): pitchwheel, control_change, note_off, note_on.
    Unknown message types are assigned the lowest priority.
    """

    def __init__(self):
        """Initialise the queue and message priority table."""
        super().__init__()
        self._seq = 0
        self._message_priority = {
            "pitchwheel": 0,
            "control_change": 1,
            "note_off": 2,
            "note_on": 3,
        }

    def push(self, item: mido.Message | mido.MetaMessage):
        """Insert a MIDI message into the priority queue.

        :param item: a :class:`mido.Message` or :class:`mido.MetaMessage` to enqueue.
        """
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

    def peek(self) -> mido.Message | mido.MetaMessage:
        """Return the highest-priority message without removing it.

        :return: the next :class:`mido.Message` or :class:`mido.MetaMessage`.
        """
        return super().peek()[-1]

    def pop(self) -> mido.Message | mido.MetaMessage:
        """Remove and return the highest-priority message.

        :return: the next :class:`mido.Message` or :class:`mido.MetaMessage`.
        """
        return super().pop()[-1]


class MIDIOutputConfig(lob.OutputInterfaceConfig):
    port: str
    send_cc: bool
    send_messages: bool
    velocity_range: list[int]
    pitchbend_range: int
    controls: dict[str, int]

    @pdt.field_validator("velocity_range")
    @classmethod
    def _valid_velocity_range(cls, v: list[int]) -> list[int]:
        if not (len(v) == 2 and 0 <= v[0] <= 127 and 0 <= v[1] <= 127 and v[0] <= v[1]):
            raise ValueError(
                f"Invalid velocity_range {v!r}. "
                "Expected [min, max] with both values in 0–127 and min <= max."
            )
        return v

    @pdt.field_validator("pitchbend_range")
    @classmethod
    def _valid_pitchbend_range(cls, v: int) -> int:
        if not 1 <= v <= 48:
            raise ValueError(
                f"Invalid pitchbend_range {v!r}. Expected an integer in 1–48."
            )
        return v

    @pdt.field_validator("controls")
    @classmethod
    def _valid_controls(cls, v: dict[str, int]) -> dict[str, int]:
        invalid = {k: cc for k, cc in v.items() if not 0 <= cc <= 127}
        if invalid:
            raise ValueError(f"CC numbers must be in 0–127, got: {invalid}")
        return v


@lp.readonly("port")
@lp.expose("_send_cc", "send_cc")
@lp.expose("_send_messages", "send_messages")
@lp.expose("_velocity_range", "velocity_range")
@lp.expose("_pitchbend_range", "pitchbend_range")
@lp.expose("_controls", "controls")
class MIDIOutput(lob.OutputInterface):
    """Output interface for MIDI playback.

    Sends note events and optionally continuous controller (CC) messages
    over a MIDI port. Supports MPE-style per-note pitch bend and
    polyphonic voice allocation across 16 channels.
    """

    config_class = MIDIOutputConfig

    def __init__(
        self,
        port: str,
        controls: dict[str, int],
        send_cc: bool,
        send_messages: bool,
        velocity_range: list[int],
        pitchbend_range: int,
        **kwargs,
    ):
        """Open a MIDI output port and initialise the playback state.

        :param port: name of the MIDI output port to open.
        :param controls: mapping of contour names to MIDI CC numbers (0–127).
        :param send_cc: whether to send CC messages for contour values.
        :param send_messages: whether to send note on/off and pitchwheel messages.
        :param velocity_range: ``[min, max]`` MIDI velocity values (0–127).
        :param pitchbend_range: pitchbend range in semitones (1–48).
        :raises ValueError: if any CC number in *controls* is outside 0–127.
        :raises ValueError: if *velocity_range* is not a valid ``[min, max]`` pair.
        :raises ValueError: if *pitchbend_range* is outside 1–48.
        """
        super().__init__(**kwargs)

        self._port = port
        self._controls = controls
        self._send_cc = send_cc
        self._send_messages = send_messages
        self._velocity_range = velocity_range
        self._pitchbend_range = pitchbend_range

        if self._active:
            self._out = self._create_output()

        self._free_channels = {i: (-np.inf, -np.inf) for i in range(16)}
        self._message_interval = 1 / 10
        self._done = threading.Event()
        self._out_lock = threading.Lock()

        if self._send_cc:
            self._cc_thread = threading.Thread(target=self._midi_cc_thread)
            if self._active:
                self._cc_thread.start()

        self._queue = MIDIQueue()

    def _create_output(self):
        return mido.open_output(self._port)

    def _midi_cc_thread(self):
        """Background thread that sends CC messages at a fixed rate.

        Runs until :meth:`reset` signals the done event. Normalises contour
        values from [0, 1] to MIDI range [0, 127] and sends one CC message
        per registered control per iteration.
        """
        logger.info("Started MIDI CC output thread.")

        while not self._done.is_set():

            messages = []
            for c in self._controls:
                if c not in self._contour_values:
                    continue

                val = max(0, min(127, int(self._contour_values[c] * 127)))

                # logger.info(f"{c}: cc {self._controls[c]} {val}")
                message = mido.Message(
                    "control_change",
                    control=self._controls[c],
                    channel=0,
                    value=val,
                )
                messages.append(message)
            with self._out_lock:
                for m in messages:
                    self._out.send(m)

            # instead of using time.sleep
            # when done is set, this terminates faster
            self._done.wait(self._message_interval)

        logger.info("Terminated MIDI CC output thread.")

    def _mpe_init(self):
        """Initialise MPE (MIDI Polyphonic Expression) pitch bend range on all 16 channels.

        Sends RPN 0 followed by a data entry message setting the bend range
        to :attr:`pitchbend_range` semitones.
        """
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

    def _event_to_midi(
        self, event, absolute_time: bool = False
    ) -> list[mido.Message | mido.MetaMessage]:
        """Convert a :class:`~loeric.core.element.LOERICElement` to a list of MIDI messages.

        Handles :class:`~loeric.core.element.Note` (with pitch bend and optional slide),
        :class:`~loeric.core.element.SongPosition`, and
        :class:`~loeric.core.element.KeySignature` events.

        :param event: the element to convert.
        :param absolute_time: if ``True``, timestamps are absolute; otherwise relative.
        :return: list of :class:`mido.Message` or :class:`mido.MetaMessage` objects.
            Returns an empty list for unrecognised or zero-duration events.
        """
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
                overall_time = le.TimeDelta(eighth_duration=event.time)

            messages = []

            bend_semitones = event._pitch - np.round(event._pitch)
            bend_percentage = bend_semitones / self._pitchbend_range

            event_velocity = event.velocity * (max_v - min_v) + min_v
            event_velocity = np.clip(event_velocity, min_v, max_v).astype(int)

            pb = min(8191, max(np.round(bend_percentage * 8191).astype(int), -8192))
            event_pitch = max(0, min(127, np.round(event.pitch).astype(int)))
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
                    note=event_pitch,
                    time=overall_time.eighth_duration,
                    channel=event.channel,
                    velocity=event_velocity,
                )
            )

            note_duration = le.TimeDelta(eighth_duration=event.duration)
            if event._is_slide:

                previous_bend = bend_percentage
                resolution = 24

                for note in event._slide_targets:
                    slide_duration = le.TimeDelta(
                        eighth_duration=note.duration / resolution
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
                    time=(overall_time + note_duration).eighth_duration,
                )
            )
            messages.append(
                mido.Message(
                    "note_off",
                    note=event_pitch,
                    channel=event.channel,
                    time=(overall_time + note_duration).eighth_duration,
                    velocity=0,
                )
            )

            return messages

        return []

    def reset(self):
        """Stop the CC thread, reset the MIDI port, and close it."""
        # stop thread
        if not self._active:
            return
        self._done.set()

        if self._send_cc and self._cc_thread.is_alive():
            self._cc_thread.join(timeout=2.0)

        with self._out_lock:
            self._out.reset()
            self._out.close()
        logger.info("Reset and closed midi output.")

    def done(self) -> bool:
        """Return whether the output message queue is empty.

        :return: ``True`` if all queued MIDI messages have been sent.
        """
        if not self._active:
            return True
        return self._queue.is_empty()

    def _allocate_channel(self, event: le.LOERICElement) -> int:
        """Allocate a free MIDI channel for a note event using voice stealing.

        Selects the first channel whose previous note has ended before *event* starts.
        If no channel is free, steals the channel with the oldest note start time.

        :param event: the note event requiring a channel.
        :return: the allocated MIDI channel number (0–15).
        """
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

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Convert events to MIDI messages and send any that are due at *tick*.

        Note events are assigned a channel via :meth:`_allocate_channel` before
        conversion. Messages are held in the internal :class:`MIDIQueue` and
        flushed in priority order up to the current tick.

        :param events: list of :class:`~loeric.core.element.LOERICElement` to process.
        :param tick: current playback position; messages with time <= tick are sent.
        """
        if not self._active or not self._send_messages:
            return

        # obtain all midi messages
        for event in events:
            if isinstance(event, le.Note):
                channel = self._allocate_channel(event)
                event.channel = channel
            for e in self._event_to_midi(event, absolute_time=True):
                self._queue.push(e)

        with self._out_lock:
            while not self._queue.is_empty():

                m = self._queue.peek()

                if m.time <= tick:

                    m = self._queue.pop()

                    if not m.is_meta:

                        if m.type in ["note_on", "note_off", "pitchwheel"]:

                            if self._send_messages:
                                self._out.send(m)
                else:
                    break
