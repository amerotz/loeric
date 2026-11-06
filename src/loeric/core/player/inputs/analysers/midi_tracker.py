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
import queue
import threading
import time
from typing import Literal

import pydantic as pdt

import loeric.core.context as lctx
import loeric.core.element as le
import loeric.core.player.inputs.analysers.midi_tracker_lib as lt
from loeric.core.player.inputs.analysers.midi import MIDIAnalyser, MIDIAnalyserConfig

logger = logging.getLogger(__name__)


def build_event_table(tune) -> lt.EventTable:
    """Group the notes of a tune into score events for the tracker.

    Notes starting at the same time form one event, and each event gets the
    user-defined chord sounding at it, if the tune has any. The whole annotated
    score is used, so a tune built with several repeats yields one long
    table.

    :param tune: the :class:`~loeric.core.tune.Tune` to track.
    :return: the event table of the tune.
    """
    elements = tune._annotated_score

    # collect the pitches sounding at each start time
    groups = {}
    for e in elements:
        if isinstance(e, le.Note):
            groups.setdefault(round(e.time.eighth_duration, 6), set()).add(
                int(round(e.pitch))
            )

    times = sorted(groups)

    # user-defined chords as (time, pitch classes); the null chord, which has
    # no root, is an empty harmony. Chords calculated at runtime by the
    # harmony module are not part of the tune and cannot be used here.
    chords = [
        (
            e.time.eighth_duration,
            [(int(e.root) + int(p)) % 12 for p in e.pitches] if e.is_valid else [],
        )
        for e in elements
        if isinstance(e, le.Chord)
    ]

    song_positions = [
        (e.position, e.time.eighth_duration)
        for e in elements
        if isinstance(e, le.SongPosition)
    ]

    return lt.EventTable(times, [groups[t] for t in times], song_positions, chords)


class MIDIScoreTrackerAnalyserConfig(MIDIAnalyserConfig):
    """Config for :class:`MIDIScoreTrackerAnalyser`.

    :param threshold: minimum confidence (0–1) for a match to be
        trusted. Lower acquires faster but may lock onto the wrong phrase.
    :param collection_seconds: minimum seconds of playing before the position
        can be acquired.
    :param confirmations: consistent matches needed to acquire the position or
        to follow a jump to another part of the tune.
    :param melody_vs_harmony_weight: weight (0–1) of the melody (top voice)
        against the harmony (all other pitches and the chords of the tune)
        when comparing played and written notes.
    """

    type: Literal["midi_tracker"]
    threshold: float = pdt.Field(ge=0.0, le=1.0)
    collection_seconds: float = pdt.Field(ge=0.0)
    confirmations: int = pdt.Field(ge=1)
    melody_vs_harmony_weight: float = pdt.Field(ge=0, le=1)


class MIDIScoreTrackerAnalyser(MIDIAnalyser):
    """MIDI analyser that tracks the position of MIDI input in the score.

    Incoming notes are timestamped on the MIDI callback thread and handed to
    a worker thread that does the alignment. When the position is acquired,
    or the performer jumps elsewhere in the tune, :meth:`get` returns a
    :class:`~loeric.core.element.UserPosition` with the new score time.
    Every time the performer's position is updated, :meth:`get` also returns a
    :class:`~loeric.core.element.UserPlayback` so that downstream code can
    compare it with the playback position.
    """

    config_class = MIDIScoreTrackerAnalyserConfig

    # base tempo used when the tune does not specify one
    _DEFAULT_QPM = 120.0
    # longest wait (seconds) of the worker for new notes
    _IDLE_TICK = 0.1
    # pause (seconds) of the worker after an unexpected error
    _ERROR_PAUSE = 0.05
    # time (seconds) to wait for the worker to stop
    _JOIN_TIMEOUT = 2.0

    def __init__(
        self,
        threshold: float,
        collection_seconds: float,
        confirmations: int,
        melody_vs_harmony_weight: float,
        **kwargs,
    ):
        """Initialise the tracker and start its worker thread.

        :param threshold: minimum confidence for a match to count.
        :param collection_seconds: minimum seconds of playing before acquiring.
        :param confirmations: consistent matches needed to acquire or jump.
        :param melody_vs_harmony_weight: weight (0–1) of the melody in the
            similarity.
        :param kwargs: forwarded to :class:`MIDIAnalyser`.
        """
        super().__init__(**kwargs)

        # Read everything that needs the LOERIC context HERE, on the main
        # thread: the context is a ContextVar and may be invisible elsewhere.
        tune = lctx.CurrentTune.get()

        qpm = self._DEFAULT_QPM
        if tune.tempos and getattr(tune.tempos[0], "qpm", None):
            qpm = float(tune.tempos[0].qpm)

        # duration of an eighth note at the base tempo
        eighth_seconds = 30.0 / qpm

        self._engine = lt.TrackerEngine(
            build_event_table(tune),
            eighth_seconds,
            threshold,
            confirmations,
            collection_seconds,
            melody_vs_harmony_weight,
            on_acquire=self._on_position,
            on_jump=self._on_position,
            on_match=self._on_match,
            log=logger.info,
        )

        self._queue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread = None

        # protects _control_events and _tracked, shared by the worker and get()
        self._lock = threading.Lock()

        # latest matched (score_time, timestamp), not yet returned by get()
        self._tracked = None

        if self._active:
            self._start_worker()

    @property
    def state(self) -> lt.TrackerState:
        """The current state of the tracker."""
        return self._engine.state

    # --------------------------------------------------------
    # MIDI CALLBACK THREAD
    # --------------------------------------------------------

    def update(self, message):
        """Queue a note-on for the worker; everything else is ignored.

        Runs on the MIDI callback thread, so it does the bare minimum.

        :param message: incoming MIDI message.
        """
        if not self._active:
            return

        if message.type != "note_on" or message.velocity == 0:
            return

        self._queue.put((time.perf_counter(), message.note))

    # --------------------------------------------------------
    # WORKER THREAD
    # --------------------------------------------------------

    def _start_worker(self):
        """Start the worker thread, unless it is already running."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop.clear()

        self._thread = threading.Thread(
            target=self._worker,
            name="score-tracker",
            daemon=True,
        )
        self._thread.start()

    def _worker(self):
        """Group queued notes, align them and acquire the position."""
        engine, q = self._engine, self._queue

        while not self._stop.is_set():
            try:
                # wake up in time to close the open note group
                deadline = engine.deadline()
                timeout = (
                    self._IDLE_TICK
                    if deadline is None
                    else min(self._IDLE_TICK, max(0.0, deadline - time.perf_counter()))
                )

                # wait for a note, then drain whatever else is queued
                items = []
                try:
                    items.append(q.get(timeout=timeout))
                    while True:
                        items.append(q.get_nowait())
                except queue.Empty:
                    pass

                # group the notes into events, then run the tracker
                events = []
                for t, pitch in items:
                    events += engine.feed(t, pitch)

                events += engine.poll(time.perf_counter())

                if events:
                    engine.process(events)
            except Exception:
                logger.exception("score tracker error")
                time.sleep(self._ERROR_PAUSE)

    def _on_position(self, result: lt.MatchResult):
        """Queue a position change, called by the engine on the worker thread.

        :param result: the new alignment result.
        """
        # TODO add start event
        with self._lock:
            self._control_events = [le.UserPosition(position=result.score_time)]

    def _on_match(self, result: lt.MatchResult):
        """Store the latest tracked position, called on the worker thread.

        Only the most recent match is kept: if several arrive between two
        calls of :meth:`get`, the older ones are superseded.

        :param result: the alignment result that updated the position.
        """
        with self._lock:
            self._tracked = (result.score_time, result.timestamp)

    # --------------------------------------------------------
    # LOERIC INTERFACE
    # --------------------------------------------------------

    def get(self) -> list[le.LOERICElement]:
        """Return and clear what the tracker produced since the last call.

        This is a :class:`~loeric.core.element.UserPosition` when the position
        is acquired or jumps, and a :class:`~loeric.core.element.UserPlayback`
        when the performer's tracked position has been updated.

        :return: list of :class:`~loeric.core.element.LOERICElement`.
        """
        # BUGFIX: read and clear atomically; an event stored by the worker
        # between the two steps used to be lost
        with self._lock:
            events, self._control_events = self._control_events, []
            tracked, self._tracked = self._tracked, None

        if tracked is not None:
            score_time, timestamp = tracked

            # delay: how long ago the performer played that position
            events.append(
                le.UserPlayback(
                    position=score_time,
                    delay=time.perf_counter() - timestamp,
                )
            )

        return events

    def reset(self):
        """Stop the worker, forget the position and start listening again."""
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=self._JOIN_TIMEOUT)

        self._engine.reset()

        with self._lock:
            self._control_events = []
            self._tracked = None

        self._queue = queue.SimpleQueue()

        # BUGFIX: the worker was never restarted, so the tracker stayed dead
        # after the first reset
        if self._active:
            self._start_worker()
