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

import numpy as np
import pydantic as pdt

import loeric.core.context as lctx
import loeric.core.element as le
import loeric.core.modules.base as lmb
import loeric.core.modules.midi_tracker_lib as lt

logger = logging.getLogger(__name__)


def build_event_table(tune) -> lt.EventTable:
    """Group the notes of a tune into score events for the tracker.

    Notes starting at the same time form one event, and each event gets the
    user-defined chord sounding at it, if the tune has any. The ids of the
    notes are kept to recognise them when they are performed. The whole
    annotated score is used, so a tune built with several repeats yields one
    long table.

    :param tune: the :class:`~loeric.core.tune.Tune` to track.
    :return: the event table of the tune.
    """
    elements = tune._annotated_score

    # collect the pitches and ids of the notes starting at each time
    pitches = {}
    ids = {}
    for e in elements:
        if isinstance(e, le.Note):
            key = round(e.time.eighth_duration, 6)
            pitches.setdefault(key, set()).add(int(round(e.pitch)))
            ids.setdefault(key, set()).add(int(e.id))

    times = sorted(pitches)

    # user-defined chords as (time, pitch classes); the null chord, which has
    # no root, is an empty harmony
    chords = [
        (
            e.time.eighth_duration,
            [(int(e.root) + int(p)) % 12 for p in e.pitches] if e.is_valid else [],
        )
        for e in elements
        if isinstance(e, le.Chord)
    ]

    return lt.EventTable(
        times,
        [pitches[t] for t in times],
        chords,
        ids=[ids[t] for t in times],
        loop_length=tune.end_time.eighth_duration - times[0],
    )


class ScoreTrackerModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`ScoreTrackerModule`.

    :param threshold: minimum confidence (0–1) for a match to be trusted.
        Lower acquires faster but may lock onto the wrong phrase.
    :param collection_seconds: minimum seconds of playing before the position
        can be acquired.
    :param confirmations: consistent matches needed to acquire the position or
        to follow a jump to another part of the tune.
    :param melody_weight: weightof the melody (top voice)
    :param harmony_weight: weightof the harmony
    :param rhythm_weight: weight of the timing consistency of a match in its
        confidence. 0 ignores the rhythm.
    """

    type: Literal["score_tracker"]
    threshold: float = pdt.Field(ge=0.0, le=1.0)
    loss_threshold: float = pdt.Field(ge=0.0, le=1.0)
    collection_seconds: float = pdt.Field(ge=0.0)
    confirmations: int = pdt.Field(ge=1)
    loss_confirmations: int = pdt.Field(ge=1)
    melody_weight: float = pdt.Field(ge=0.0)
    harmony_weight: float = pdt.Field(ge=0.0)
    rhythm_weight: float = pdt.Field(ge=0.0)
    confidence_contour: str


class ScoreTrackerModule(lmb.LOERICModule):
    """Module that tracks the position of the performer in the score.

    It goes at the END of the pipeline, so that it sees the tune as it is
    performed: the notes with their final timing, and the chords, whether
    written in the tune or calculated by the harmony module. The played notes
    are forwarded to it as :class:`~loeric.core.element.UserNote` elements,
    for example by :class:`~loeric.core.player.inputs.analysers.midi_forward.MIDINoteForwarder`.

    The alignment is too slow to run on the tick of the performance, so it is
    done by a worker thread. The module only hands elements over to it and
    collects its results, which takes no time. It produces:

    - a :class:`~loeric.core.element.UserPosition` when the position is
      acquired or the performer jumps elsewhere in the tune;
    - a :class:`~loeric.core.element.UserPlayback` every time the performer's
      position is updated, with how fast they play compared to the
      performance.
    """

    config_class = ScoreTrackerModuleConfig

    # base tempo used when the tune does not specify one
    _DEFAULT_QPM = 120.0
    # longest wait (seconds) of the worker for new items
    _IDLE_TICK = 0.1
    # pause (seconds) of the worker after an unexpected error
    _ERROR_PAUSE = 0.05
    # time (seconds) to wait for the worker to stop
    _JOIN_TIMEOUT = 2.0
    # tempo changes smaller than this (quarters per minute) are not reported
    _TEMPO_EPSILON = 0.01

    def __init__(
        self,
        threshold: float,
        loss_threshold: float,
        collection_seconds: float,
        confirmations: int,
        loss_confirmations: int,
        melody_weight: float,
        harmony_weight: float,
        rhythm_weight: float,
        confidence_contour: str,
        **kwargs,
    ):
        """Initialise the module; the tracker starts with the first element.

        :param threshold: minimum confidence for a match to count.
        :param collection_seconds: minimum seconds of playing before acquiring.
        :param confirmations: consistent matches needed to acquire or jump.
        :param melody_vs_harmony_weight: weight (0–1) of the melody in the
            similarity.
        :param rhythm_weight: weight of the timing consistency in the
            confidence.
        :param kwargs: forwarded to :class:`~loeric.core.modules.base.LOERICModule`.
        """
        super().__init__(**kwargs)

        self._name = "score_tracker"

        self._threshold = threshold
        self._loss_threshold = loss_threshold

        self._collection_seconds = collection_seconds

        self._confirmations = confirmations
        self._loss_confirmations = loss_confirmations

        self._melody_weight = melody_weight
        self._harmony_weight = harmony_weight
        self._rhythm_weight = rhythm_weight
        self._confidence_contour = confidence_contour

        # created with the first element, when the tune is known
        self._engine = None

        self._queue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread = None

        # protects and _tracked, shared by the worker and the tick
        self._lock = threading.Lock()

        # latest matched (score_time, timestamp), not yet emitted
        self._tracked = None
        # whether we are tracking or not
        self._position_known = False

        # last tempo told to the worker
        self._last_qpm = None
        self._min_confidence = np.inf
        self._max_confidence = -np.inf

    @property
    def _state(self) -> lt.TrackerState:
        """The current state of the tracker, or ``None`` before it starts."""
        return None if self._engine is None else self._engine.state

    # --------------------------------------------------------
    # TICK THREAD
    # --------------------------------------------------------

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Hand the element over to the worker and collect its results.

        This runs on every tick, so it only moves data around.

        :param element: the element to process.
        :param window: unused.
        :return: the element (unless it is a played note, which is consumed)
            followed by the position elements produced by the worker.
        """
        self._ensure_running()

        out = [element]

        if isinstance(element, le.UserNote):
            # a note played by the performer: consume it
            self._queue.put(("played", element.wall_time, element.pitch))
            out = []

        elif isinstance(element, le.Note):
            # a note of the performance, with its final time
            self._queue.put(("performed", element.id, element.time.eighth_duration))

        elif isinstance(element, le.Chord):
            # a chord of the performance, written or calculated
            pitch_classes = []
            if element.is_valid:
                pitch_classes = [
                    (int(element.root) + int(p)) % 12 for p in element.pitches
                ]

            self._queue.put(("chord", pitch_classes))

        self._send_tempo()

        out += self._collect()

        return out

    def _send_tempo(self):
        """Tell the worker when the tempo of the performance changes."""
        if self._tempo is None:
            return

        qpm = float(self._tempo.qpm)

        if self._last_qpm is None or abs(qpm - self._last_qpm) > self._TEMPO_EPSILON:
            self._last_qpm = qpm
            self._queue.put(("tempo", qpm))

    def _collect(self) -> list[le.LOERICElement]:
        """Turn the results of the worker into elements.

        :return: the elements produced since the last call.
        """
        with self._lock:
            tracked, self._tracked = self._tracked, None
            unknown_pending = self._position_known is False

            if unknown_pending:
                self._position_known = None

        out = []

        if unknown_pending:
            out.append(le.UnknownUserPosition())

        if tracked is not None:
            score_time, timestamp, jump, confidence = tracked

            # delay: how long ago the performer played that position
            out.append(
                le.UserPlayback(score_time=score_time, timestamp=timestamp, jump=jump)
            )
            self._min_confidence = min(confidence, self._min_confidence)
            self._max_confidence = max(confidence, self._max_confidence)
            if self._min_confidence != self._max_confidence:
                confidence = (confidence - self._min_confidence) / (
                    self._max_confidence - self._min_confidence
                )
                out.append(
                    le.ContourValue(name=self._confidence_contour, value=confidence)
                )

        return out

    def _ensure_running(self):
        """Create the engine and start the worker, if needed."""
        if self._engine is None:
            # the tune is known in the context by now; the table is built
            # with the first element, before the performance changes it
            tune = lctx.CurrentTune.get()

            qpm = self._DEFAULT_QPM
            if tune.tempos and getattr(tune.tempos[0], "qpm", None):
                qpm = float(tune.tempos[0].qpm)

            self._engine = lt.TrackerEngine(
                build_event_table(tune),
                30.0 / qpm,
                self._threshold,
                self._loss_threshold,
                self._confirmations,
                self._loss_confirmations,
                self._collection_seconds,
                self._melody_weight,
                self._harmony_weight,
                self._rhythm_weight,
                on_acquire=self._on_match,
                on_jump=self._on_jump,
                on_match=self._on_match,
                on_loss=self._on_loss,
                log=logger.info,
            )

        if self._thread is None:
            self._stop.clear()

            self._thread = threading.Thread(
                target=self._worker,
                name="score-tracker",
                daemon=True,
            )
            self._thread.start()

    # --------------------------------------------------------
    # WORKER THREAD
    # --------------------------------------------------------

    def _worker(self):
        """Group played notes, align them and acquire the position."""
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

                # wait for something, then drain whatever else is queued
                items = []
                try:
                    items.append(q.get(timeout=timeout))
                    while True:
                        items.append(q.get_nowait())
                except queue.Empty:
                    pass

                # tell the engine what happened, in order
                events = []
                for kind, *args in items:
                    if kind == "played":
                        events += engine.feed(*args)
                    elif kind == "performed":
                        engine.observe_note(*args)
                    elif kind == "chord":
                        engine.set_chord(*args)
                    elif kind == "tempo":
                        engine.set_tempo(*args)

                events += engine.poll(time.perf_counter())

                if events:
                    engine.process(events)
            except Exception:
                logger.exception("score tracker error")
                time.sleep(self._ERROR_PAUSE)

    def _on_match(self, result: lt.MatchResult):
        """Store the latest tracked position, called on the worker thread.

        Only the most recent match is kept: if several arrive between two
        ticks, the older ones are superseded.

        :param result: the alignment result that updated the position.
        """
        with self._lock:
            self._position_known = True
            self._tracked = (
                result.score_time,
                result.timestamp,
                False,
                result.confidence,
            )

    def _on_jump(self, result: lt.MatchResult):
        with self._lock:
            self._position_known = False
            self._tracked = (
                result.score_time,
                result.timestamp,
                True,
                result.confidence,
            )

    def _on_loss(self):
        """Store a position loss, called by the engine on the worker thread."""
        with self._lock:
            self._tracked = None
            self._position_known = False

    # --------------------------------------------------------
    # LOERIC INTERFACE
    # --------------------------------------------------------

    def reset(self):
        """Stop the worker and forget the position.

        The worker starts again with the next element.
        """
        super().reset()

        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=self._JOIN_TIMEOUT)
            self._thread = None

        if self._engine is not None:
            self._engine.reset()

        with self._lock:
            self._tracked = None

        self._queue = queue.SimpleQueue()
        self._last_qpm = None
