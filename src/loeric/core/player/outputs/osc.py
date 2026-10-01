import logging
import random
import threading
from collections.abc import Iterable
from typing import Union

import numpy as np
import pydantic as pdt
from pythonosc.osc_message import OscMessage
from pythonosc.osc_message_builder import ArgValue, OscMessageBuilder
from pythonosc.udp_client import SimpleUDPClient

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.outputs.base as lob

logger = logging.getLogger(__name__)


class OSCQueue(le.Queue):
    """A priority queue of OSC messages.

    Message type priority (lowest first):
    Unknown message types are assigned the lowest priority.
    """

    def __init__(self):
        """Initialise the queue and message priority table."""
        super().__init__()
        self._seq = 0

    def push(self, item: tuple(OscMessage, le.TimeDelta)):
        """Insert an OSC message into the priority queue.

        :param item: a :class:`mido.Message` or :class:`mido.MetaMessage` to enqueue.
        """
        item, time = item

        super().push(
            (
                time,
                self._seq,
                item,
            )
        )
        self._seq += 1

    def peek(self) -> OscMessage:
        """Return the highest-priority message without removing it.

        :return: the next :class:`OscMessage`.
        """
        time, _, item = super().peek()
        return item, time

    def pop(self) -> OscMessage:
        """Remove and return the highest-priority message.

        :return: the next :class:`OscMessage`.
        """
        time, _, item = super().pop()
        return item, time


class OSCOutputConfig(lob.OutputInterfaceConfig):

    server: str
    port: int
    controls: dict[str, str]
    velocity_range: list[int]
    pitchbend_range: int
    send_cc: bool
    send_messages: bool
    control_messages_per_second: float

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


@lp.readonly("server")
@lp.readonly("port")
@lp.expose("_velocity_range", "velocity_range")
@lp.expose("_pitchbend_range", "pitchbend_range")
@lp.expose("_send_cc", "send_cc")
@lp.expose("_send_messages", "send_messages")
@lp.expose("_control_messages_per_second", "control_messages_per_second")
@lp.expose("_controls", "controls")
class OSCOutput(lob.OutputInterface):

    config_class = OSCOutputConfig

    def __init__(
        self,
        server: str,
        port: int,
        controls: dict[str, str],
        velocity_range: list[int],
        pitchbend_range: int,
        send_cc: bool,
        send_messages: bool,
        control_messages_per_second: float,
        **kwargs,
    ):

        super().__init__(**kwargs)

        self._server = server
        self._port = port
        self._controls = controls
        self._send_cc = send_cc
        self._send_messages = send_messages
        self._velocity_range = velocity_range
        self._pitchbend_range = pitchbend_range

        self._control_messages_per_second = control_messages_per_second
        self._message_interval = 1 / self._control_messages_per_second

        self._prefix = "loeric"

        if self._active:
            self._out = SimpleUDPClient(self._server, self._port)

        self._done = threading.Event()
        self._out_lock = threading.Lock()

        if self._send_cc:
            self._cc_thread = threading.Thread(target=self._osc_cc_thread)
            if self._active:
                self._cc_thread.start()

        self._queue = OSCQueue()

    # override expose decorator
    def _set_control_messages_per_second(self, control_messages_per_second):
        # update both value and interval
        self._control_messages_per_second = control_messages_per_second
        self._message_interval = 1 / self._control_messages_per_second

    def _build_osc_message(
        self, address: str, value: Union[ArgValue, Iterable[ArgValue]]
    ):
        builder = OscMessageBuilder(address=address)

        if value is None:
            pass

        elif not isinstance(value, Iterable) or isinstance(value, (str, bytes)):
            builder.add_arg(value)

        else:
            for val in value:
                builder.add_arg(val)

        msg = builder.build()

        return msg

    def _event_to_osc(
        self, event, absolute_time: bool = False
    ) -> list[tuple(OscMessage, le.TimeDelta)]:

        time = event.duration
        if absolute_time:
            time += event.time

        if isinstance(event, le.SongPosition):
            return [
                (
                    self._build_osc_message(f"/{self._prefix}/songpos", event.position),
                    event.time,
                )
            ]

        elif isinstance(event, le.KeySignature):
            return [
                (
                    self._build_osc_message(
                        f"/{self._prefix}/key", le.NOTE_NAMES[event.major_root]
                    ),
                    event.time,
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

            bend_semitones = event.pitch - np.round(event.pitch)
            bend_percentage = bend_semitones / self._pitchbend_range

            event_velocity = event.velocity * (max_v - min_v) + min_v
            event_velocity = np.clip(event_velocity, min_v, max_v).astype(int)

            pb = int(min(8191, max(np.round(bend_percentage * 8191), -8192)))
            event_pitch = int(max(0, min(127, np.round(event.pitch))))

            messages.append(
                (
                    self._build_osc_message("/loeric/pitchwheel", (event_pitch, pb)),
                    overall_time,
                )
            )
            messages.append(
                (self._build_osc_message("/loeric/note_on/", event_pitch), overall_time)
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
                            (
                                self._build_osc_message(
                                    "/loeric/pitchwheel", (event_pitch, pb)
                                ),
                                overall_time,
                            )
                        )
                        note_duration = note_duration - slide_duration

                    previous_bend = bend_percentage

            if event._duration == 0:
                note_duration += 0.001

            messages.append(
                (
                    self._build_osc_message("/loeric/pitchwheel", (event_pitch, pb)),
                    overall_time + note_duration,
                )
            )
            messages.append(
                (
                    self._build_osc_message("/loeric/note_off/", event_pitch),
                    overall_time + note_duration,
                )
            )

            return messages

        return []

        pass

    def _osc_cc_thread(self):
        """Background thread that sends osc messages at a fixed rate.

        Runs until :meth:`reset` signals the done event.
        """
        logger.info("Started OSC control output thread.")

        while not self._done.is_set():

            messages = []
            for c in self._controls:
                if c not in self._contour_values:
                    continue

                val = self._contour_values[c]

                # logger.info(f"{c}: cc {self._controls[c]} {val}")
                message = self._build_osc_message(self._controls[c], val)
                messages.append(message)
            with self._out_lock:
                for m in messages:
                    self._out.send(m)

            # instead of using time.sleep
            # when done is set, this terminates faster
            self._done.wait(self._message_interval)

        logger.info("Terminated OSC control output thread.")

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Convert events to OSC messages and send any that are due at *tick*.

        Messages are held in the internal :class:`OSCQueue` and
        flushed in priority order up to the current tick.

        :param events: list of :class:`~loeric.core.element.LOERICElement` to process.
        :param tick: current playback position; messages with time <= tick are sent.
        """
        if not self._active or not self._send_messages:
            return

        # obtain all midi messages
        for event in events:

            if isinstance(event, le.Note):
                pass

            for e in self._event_to_osc(event, absolute_time=True):
                self._queue.push(e)

        with self._out_lock:

            while not self._queue.is_empty():

                m, t = self._queue.peek()

                if t <= tick:
                    m, _ = self._queue.pop()

                    if self._send_messages:
                        self._out.send(m)

                else:
                    break

    def reset(self):
        """Stop the CC thread, reset the OSC port, and close it."""
        # stop thread
        if not self._active:
            return
        self._done.set()

        if self._send_cc and self._cc_thread.is_alive():
            self._cc_thread.join(timeout=2.0)

        with self._out_lock:
            self._out.close()

        logger.info("Reset and closed OSC output.")

    def done(self) -> bool:
        """Return whether the output message queue is empty.

        :return: ``True`` if all queued OSC messages have been sent.
        """
        if not self._active:
            return True
        return self._queue.is_empty()
