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
import multiprocessing as mp
import os
import random
import sys
import threading
import time
from multiprocessing import shared_memory

import mido
import numpy as np
import pandas as pd
import pyaudio
import sounddevice as sd
import tinysoundfont

import loeric.core.element as le
import loeric.core.paths as lp

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    logger.error(
        "Could not find packages PyQt-related packages. The 'VisualOutput' port will not be available."
    )
    PYQT_AVAILABLE = False


@lp.readonly("active")
@lp.readonly("type")
class OutputInterface:
    """Abstract base for all output interfaces.

    Subclasses represent concrete output modalities (MIDI, visual, data, etc.)
    and expose a uniform :meth:`play_events` / :meth:`set` / :meth:`reset` /
    :meth:`done` interface to the player.
    """

    _active: bool
    _type: str

    def __init__(self, name: str):
        """Initialise the output interface.

        :param name: identifier for this interface instance.
        """
        self._contour_values = {}
        self._name = name
        self._active = True
        self._type = "uninitialised"

    @staticmethod
    def create_output(config: dict, name: str = None) -> "OutputInterface":
        """Instantiate the appropriate output interface from a config dict.

        :param config: interface configuration. Must contain ``active`` and ``type`` keys.
        :param name: identifier passed to the created interface.
        :return: a concrete :class:`OutputInterface` subclass instance,
            or an inactive :class:`OutputInterface` if ``active`` is false.
        :raises ValueError: if ``config["type"]`` is not recognised.
        """
        if not config["active"]:
            interface = OutputInterface(name=None)
            interface._active = False
            return interface

        if config["type"] == "midi":
            return MIDIOutput(
                name=name,
                port=config["port"],
                controls=config["controls"],
                send_cc=config["send_cc"],
                send_messages=config["send_messages"],
                velocity_range=config["velocity_range"],
                pitchbend_range=config["pitchbend_range"],
            )
        elif config["type"] == "soundfont":
            return SoundfontOutput(
                name=name,
                path=config["path"],
                program=config["program"],
                gain=config["gain"],
                device=config["device"],
                controls=config["controls"],
                send_cc=config["send_cc"],
                send_messages=config["send_messages"],
                velocity_range=config["velocity_range"],
                pitchbend_range=config["pitchbend_range"],
                samplerate=config["samplerate"],
            )

        elif config["type"] == "visual" and PYQT_AVAILABLE:
            return VisualOutput(
                name=name,
                width=config["width"],
                height=config["height"],
                window_size=config["window_size"],
                fps=config["fps"],
                controls=config["controls"],
            )
        elif config["type"] == "data":
            return DataOutput(
                name=name,
                file_format=config["format"],
                path=config["path"],
                controls=config["controls"],
            )

        else:
            raise ValueError(f"Unknown output interface type {config['type']}.")

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Send a list of events to the output at the given tick.

        :param events: list of :class:`~loeric.core.element.LOERICElement` to send.
        :param tick: current playback position as a :class:`~loeric.core.element.TimeDelta` or float.
        """
        pass

    def reset(self):
        """Reset the output to its initial state, releasing any held resources."""
        pass

    def set(self, contour_values: dict):
        """Update the internal contour value store.

        :param contour_values: mapping of contour names to their current float values.
        """
        self._contour_values.update(contour_values)

    def done(self) -> bool:
        """Return whether all pending output has been flushed.

        :return: ``True`` if the output queue is empty and the interface is idle.
        """
        return True


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


def _valid_velocity_range(v: list) -> bool:
    return (
        isinstance(v, list)
        and len(v) == 2
        and all(isinstance(x, int) for x in v)
        and 0 <= v[0] <= 127
        and 0 <= v[1] <= 127
        and v[0] <= v[1]
    )


def _valid_pitchbend_range(v: int) -> bool:
    return isinstance(v, int) and 1 <= v <= 48


def _valid_controls(v: dict) -> bool:
    return (
        isinstance(v, dict)
        and all(isinstance(k, str) for k in v)
        and all(isinstance(cc, int) and 0 <= cc <= 127 for cc in v.values())
    )


@lp.readonly("port")
@lp.expose("_send_cc", "send_cc", validator=lambda v: isinstance(v, bool))
@lp.expose("_send_messages", "send_messages", validator=lambda v: isinstance(v, bool))
@lp.expose("_velocity_range", "velocity_range", validator=_valid_velocity_range)
@lp.expose("_pitchbend_range", "pitchbend_range", validator=_valid_pitchbend_range)
@lp.expose("_controls", "controls", validator=_valid_controls)
class MIDIOutput(OutputInterface):
    """Output interface for MIDI playback.

    Sends note events and optionally continuous controller (CC) messages
    over a MIDI port. Supports MPE-style per-note pitch bend and
    polyphonic voice allocation across 16 channels.
    """

    _send_cc: bool
    _send_messages: bool
    _velocity_range: list[int]
    _pitchbend_range: list[int]
    _controls: dict[str, int]

    def __init__(
        self,
        name: str,
        port: str,
        controls: dict[str, int],
        send_cc: bool,
        send_messages: bool,
        velocity_range: list[int],
        pitchbend_range: int,
    ):
        """Open a MIDI output port and initialise the playback state.

        :param name: identifier for this interface instance.
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
        super().__init__(name)

        if not _valid_controls(controls):
            raise ValueError(
                f"Invalid controls mapping {controls!r}. "
                "Keys must be strings and values must be integers in 0–127."
            )
        if not _valid_velocity_range(velocity_range):
            raise ValueError(
                f"Invalid velocity_range {velocity_range!r}. "
                "Expected [min, max] with both values in 0–127 and min <= max."
            )
        if not _valid_pitchbend_range(pitchbend_range):
            raise ValueError(
                f"Invalid pitchbend_range {pitchbend_range!r}. Expected an integer in 1–48."
            )

        self._type = "midi"

        self._port = port
        self._controls = controls
        self._send_cc = send_cc
        self._send_messages = send_messages
        self._velocity_range = velocity_range
        self._pitchbend_range = pitchbend_range

        self._out = self._create_output()

        self._free_channels = {i: (-np.inf, -np.inf) for i in range(16)}
        self._message_interval = 1 / 10
        self._done = threading.Event()
        self._out_lock = threading.Lock()

        if self._send_cc:
            self._cc_thread = threading.Thread(target=self._midi_cc_thread)
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
                overall_time = le.TimeDelta(eighth_duration=event._time.eighth_duration)

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
        if not self._send_messages:
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


if PYQT_AVAILABLE:

    @lp.readonly("window_size")
    @lp.readonly("width")
    @lp.readonly("height")
    @lp.readonly("fps")
    @lp.readonly("controls")
    class VisualOutput(OutputInterface):
        """Output interface for real-time graphical display of contour values.

        Renders contour signals as scrolling waveforms in a PyQtGraph window
        running in a separate process. Communicates with the GUI process via
        shared memory.

        Only available when PyQt and PyQtGraph are installed.
        """

        def __init__(
            self,
            name: str,
            width: int,
            height: int,
            window_size: int,
            fps: int,
            controls: list[str],
        ):
            """Open a graphical output window in a child process.

            :param name: identifier for this interface instance.
            :param width: window width in pixels.
            :param height: window height in pixels.
            :param window_size: number of samples shown in the scrolling plot.
            :param fps: target refresh rate in frames per second.
            :param controls: list of contour names to display.
            """
            super().__init__(name)

            self._type = "visual"
            self._width = width
            self._height = height
            self._fps = fps
            self._controls = controls
            self._time_interval = 1000 // fps
            self._window_size = window_size

            # create gui process
            self._process = mp.Process(
                target=self._graphic_loop, name="LOERIC visual", daemon=True
            )
            self._process.start()

            # create shared memory
            array = np.ones(len(self._controls), dtype=float)

            self._memory = shared_memory.SharedMemory(
                name="loeric-visual-shared-memory",
                create=True,
                size=sys.getsizeof(array),
            )

            # create shared buffer
            self._array = np.ndarray(
                array.shape, dtype=array.dtype, buffer=self._memory.buf
            )

        def _graphic_loop(self):
            """Entry point for the child GUI process.

            Attaches to shared memory, creates the PyQtGraph window, and runs
            the Qt event loop. Closes shared memory on exit.
            """
            # attach to shared memory
            array = np.ones(len(self._controls), dtype=float)
            self._memory = shared_memory.SharedMemory(
                name="loeric-visual-shared-memory", size=sys.getsizeof(array)
            )
            # create shared buffer
            self._array = np.ndarray(
                array.shape, dtype=array.dtype, buffer=self._memory.buf
            )

            try:
                # create app
                app = QtWidgets.QApplication([])

                win = pg.GraphicsLayoutWidget(
                    show=True, size=(self._width, self._height)
                )
                plot = win.addPlot(title="Real-Time Signal")
                plot.enableAutoRange(y=False)
                plot.setYRange(0, 1)

                self._curves = {
                    c: plot.plot(
                        pen=pg.mkPen(
                            "#{:06x}".format(random.randint(0, 0xFFFFFF)), width=2
                        )
                    )
                    for c in self._controls
                }

                self._x = np.arange(self._window_size)
                self._ys = {c: np.zeros(self._window_size) for c in self._controls}

                self._timer = QtCore.QTimer()
                self._timer.timeout.connect(self._update)
                self._timer.start(self._time_interval)  # ~60 FPS

                app.exec()
            except Exception:
                self._memory.close()

        def _update(self):
            """Qt timer callback that shifts the scrolling buffers and redraws all curves."""
            for i, c in enumerate(self._controls):
                self._ys[c][:-1] = self._ys[c][1:]
                self._ys[c][-1] = self._array[i]
                self._curves[c].setData(self._x, self._ys[c])

        def play_events(
            self, events: list[le.LOERICElement], tick: le.TimeDelta | float
        ):
            """Send events to the output."""
            pass

        def reset(self):
            """Reset output state."""
            while self._process.is_alive():
                self._process.terminate()
            self._process.close()
            self._memory.close()
            self._memory.unlink()

        def done(self) -> bool:
            """Return ``True``; the visual output has no pending message queue.

            :return: always ``True``.
            """
            return True

        def set(self, contour_values: dict):
            """Write current contour values into shared memory for the GUI process.

            :param contour_values: mapping of contour names to float values in [0, 1].
            """
            for i, c in enumerate(self._controls):
                if c in self._controls:
                    self._array[i] = contour_values[c]


@lp.expose("_path", "path")
@lp.expose("_format", "format", validator=lambda x: x in DataOutput.formats)
@lp.expose("_controls", "controls")
class DataOutput(OutputInterface):
    """Output interface that records contour values to a file.

    Samples contour values at a fixed rate in a background thread and writes
    the accumulated data to disk in the chosen format when :meth:`done` is called.

    Supported formats are listed in :attr:`formats`.
    """

    _path: str
    _format: str
    _controls: list[str]

    formats: list[str] = [
        "pickle",
        "csv",
        "excel",
        "json",
        "html",
        "xml",
        "latex",
        "feather",
        "parquet",
        "iceberg",
        "orc",
        "sql",
        "stata",
    ]

    def __init__(self, name: str, file_format: str, path: str, controls: list[str]):
        """Initialise the data output and start the background recording thread.

        :param name: identifier for this interface instance.
        :param file_format: output file format; must be a value in :attr:`formats`.
        :param path: destination file path.
        :param controls: list of contour names to record.
        :raises AssertionError: if *file_format* is not in :attr:`formats`.
        """
        super().__init__(name)

        self._type = "data"
        self._format = file_format
        self._path = path
        self._controls = controls
        self._append_index = 0
        self._thread = threading.Thread(target=self._data_thread)
        self._done = threading.Event()
        self._done_saving = threading.Event()
        self._message_interval = 1 / 10

        assert self._format in DataOutput.formats, f"Unsupported format {self._format}."

        self._df = pd.DataFrame(columns=["contour", "time", "value"])

        self._thread.start()

    def _data_thread(self):
        """Add contour values to database every fixed interval.

        Serialise the internal DataFrame to the configured format
        and path when the player asks to be done.
        """
        idx = 0
        df = self._df
        controls = self._controls
        contour_values = self._contour_values

        while not self._done.is_set():

            # current time
            t = time.perf_counter()

            # add all relevant contours
            for c in contour_values:
                if c in controls:
                    df.loc[idx] = [c, t, contour_values[c]]
                    idx += 1

            self._done.wait(self._message_interval)

        # save
        getattr(self._df, f"to_{self._format}")(self._path, index=False)

        logger.info(f"Saved to {self._path}.")
        self._done_saving.set()

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Send events to the output."""
        pass

    def reset(self):
        """Reset output state."""
        while self._thread.is_alive():
            self._done.set()

        self._done.clear()
        self._append_index = 0
        self._df = pd.DataFrame(columns=["contour", "time", "value"])
        self._done.clear()

    def done(self) -> bool:
        """Stop the recording thread and check if it is done saving.

        :return: whether the thread has saved the file
        """
        self._done.set()

        return self._done_saving.is_set()


class _SynthOutput(mido.ports.BaseOutput):

    def __init__(
        self, name: str, path: str, program: int, gain: float, device: str, **kwargs
    ):

        self._name = name
        self._path = path
        self._program = program
        self._gain = gain

        self._synth = tinysoundfont.Synth()
        self._soundfont_id = self._synth.sfload(self._path, gain=self._gain)

        # find audio device index
        p = pyaudio.PyAudio()
        device_index = None
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if device == info["name"]:
                device_index = i
                logger.info(f"Found audio device {info['name']} (index={i}).")
                break
        p.terminate()
        if device_index is None:
            logger.error(f"Audio device {device} not found.")

        # start synth
        self._synth.start(output_device_index=device_index)
        self._synth_is_running = True

        # select the right program
        for channel in range(16):
            self._synth.program_select(channel, self._soundfont_id, 0, self._program)

        # init the output
        mido.ports.BaseOutput.__init__(self, name=self._name, **kwargs)

    def _send(self, msg):
        if msg.type == "note_on":
            self._synth.noteon(msg.channel, msg.note, msg.velocity)
        elif msg.type == "note_off":
            self._synth.noteoff(msg.channel, msg.note)
        elif msg.type == "pitchwheel":
            self._synth.pitchbend(msg.channel, msg.pitch + 8192)
        elif msg.type == "control_change":
            self._synth.control_change(msg.channel, msg.control, msg.value)
        else:
            logger.warning(
                "\033[38;2;255;255;0m[WARN]\tUnknown MIDI message type: ",
                msg.type,
                "\033[0m",
            )

    def close(self):
        # unload the soundfont
        if self._synth_is_running:
            if self._soundfont_id is not None:
                self._synth.sfunload(self._soundfont_id)

            # stop the synth
            self._synth.stop()
            self._synth_is_running = False

        # close the output port
        super().close()


@lp.readonly("program")
@lp.readonly("path")
@lp.readonly("gain")
@lp.readonly("samplerate")
@lp.readonly("device")
class SoundfontOutput(MIDIOutput):

    _program: int
    _gain: float

    def __init__(
        self,
        name: str,
        path: str,
        program: int,
        gain: float,
        device: str,
        send_cc: bool,
        send_messages: bool,
        velocity_range: list[int],
        pitchbend_range: int,
        controls: dict[str, int],
        samplerate: int,
    ):

        assert os.path.isfile(path), f"'{path}' is not a valid path."

        self._path = path
        self._program = program
        self._controls = controls
        self._gain = gain
        self._soundfont_id = None
        self._device = device
        self._samplerate = samplerate

        super().__init__(
            name=name,
            port=None,
            controls=controls,
            send_cc=send_cc,
            send_messages=send_messages,
            velocity_range=velocity_range,
            pitchbend_range=pitchbend_range,
        )

        # unused
        del self._port

    def _create_output(self):
        """Load the soundfont."""
        return SynthOutput(
            name="LOERIC Synth",
            path=self._path,
            program=self._program,
            gain=self._gain,
            device=self._device,
            samplerate=self._samplerate,
        )


class SynthOutput(mido.ports.BaseOutput):
    def __init__(
        self,
        name: str,
        path: str,
        program: int,
        gain: float,
        device: str,
        samplerate: int,
        **kwargs,
    ):
        self._name = name
        self._path = path
        self._program = program
        self._gain = gain
        self._device = device
        self._lock = threading.RLock()
        self._samplerate = samplerate

        self._synth = tinysoundfont.Synth(gain=self._gain, samplerate=self._samplerate)
        self._soundfont_id = self._synth.sfload(self._path)
        self._stream = None
        self._synth_is_running = False

        device_index = None
        for i, info in enumerate(sd.query_devices()):
            if info["max_output_channels"] > 0 and info["name"] == device:
                device_index = i
                logger.info(f"Found audio device {info['name']} (index={i}).")
                break

        if device_index is None:
            raise RuntimeError(f"Audio device {device} not found.")

        for channel in range(16):
            self._synth.program_select(channel, self._soundfont_id, 0, self._program)

        def callback(outdata, frames, time, status):
            if status:
                logger.warning("Audio callback status: %s", status)
            with self._lock:
                buf = self._synth.generate(samples=frames)
            outdata[:] = buf

        self._stream = sd.RawOutputStream(
            samplerate=self._synth.samplerate,
            blocksize=1024,
            device=device_index,
            channels=2,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        self._synth_is_running = True

        mido.ports.BaseOutput.__init__(self, name=self._name, **kwargs)

    def _send(self, msg):
        with self._lock:
            if msg.type == "note_on":
                if msg.velocity == 0:
                    self._synth.noteoff(msg.channel, msg.note)
                else:
                    self._synth.noteon(msg.channel, msg.note, msg.velocity)
            elif msg.type == "note_off":
                self._synth.noteoff(msg.channel, msg.note)
            elif msg.type == "pitchwheel":
                self._synth.pitchbend(msg.channel, msg.pitch + 8192)
            elif msg.type == "control_change":
                self._synth.control_change(msg.channel, msg.control, msg.value)
            else:
                logger.warning("Unknown MIDI message type: %s", msg.type)

    def close(self):
        if self._synth_is_running:
            with self._lock:
                self._synth.sounds_off()
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if self._soundfont_id is not None:
                self._synth.sfunload(self._soundfont_id)
            self._synth_is_running = False

        super().close()
