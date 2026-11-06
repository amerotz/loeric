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

"""Score-position tracking core.

Pure numpy: it has no LOERIC imports and no context access, so it can be
tested on its own. All score times are in eighth notes (LOERIC's unit); all
wall-clock times are seconds from :func:`time.perf_counter`.

The pipeline is:

1. :class:`NoteGrouper` turns raw note-ons into chord-like input events.
2. :class:`Follower` aligns the recent input events against the score.
3. :class:`Tracker` collects consistent alignments while searching.
4. :class:`TrackerEngine` ties everything together and decides when the
   position is acquired and when it has jumped.
"""

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

# ============================================================
# DATA
# ============================================================


@dataclass
class InputEvent:
    """A group of simultaneous notes played by the performer.

    :param timestamp: wall-clock time of the first note of the group.
    :param pc: 12-element pitch-class presence vector.
    :param top_pc: pitch class of the highest note (the melody voice).
    """

    timestamp: float
    pc: np.ndarray
    top_pc: int


@dataclass
class MatchResult:
    """The outcome of aligning the played events against the score.

    :param position: index of the score event matching the last played event.
    :param score_time: score time of that event, in eighth notes.
    :param song_position: id of the closest song position marker.
    :param song_offset: distance from that marker, in eighth notes.
    :param confidence: alignment confidence in [0, 1].
    :param timestamp: wall-clock time of the last matched played event.
    """

    position: int
    score_time: float
    song_position: int
    song_offset: float
    confidence: float
    timestamp: float


@dataclass
class Evidence:
    """One confident alignment collected while searching.

    :param timestamp: wall-clock time of the match.
    :param beat: score time elapsed since the first piece of evidence.
    :param confidence: confidence of the match.
    :param position: score event index of the match.
    """

    timestamp: float
    beat: float
    confidence: float
    position: int


@dataclass
class TrackerState:
    """The public state of the tracker.

    :param mode: either ``"SEARCHING"`` or ``"ACQUIRED"``.
    :param result: last accepted alignment, if any.
    """

    mode: str
    result: MatchResult | None = None


# ============================================================
# EVENT TABLE
# ============================================================


class EventTable:
    """Score representation used by the tracker.

    Score times are shifted so that the first event happens at time zero.
    """

    def __init__(self, times, pitches, song_positions, chords=None):
        """Initialise the table.

        :param times: score time of each event, in eighth notes.
        :param pitches: for each event, the MIDI pitches sounding at it.
        :param song_positions: list of ``(id, time)`` song position markers.
        :param chords: optional user-defined chords, as a list of
            ``(time, pitch classes)``. A chord lasts until the next one; an
            empty pitch class list is the null chord (no harmony).
        :raises ValueError: if the table is empty or an event has no pitch.
        """
        self.times = np.asarray(times, dtype=np.float64)

        if len(self.times) == 0:
            raise ValueError("Empty event table.")

        # shift the score so that it starts at zero
        start = float(self.times[0])
        self.times = self.times - start

        self.pitches = [frozenset(int(p) for p in ps) for ps in pitches]
        self.n = len(self.pitches)

        # the chord sounding at each event (empty if there is none): the
        # last one that started at or before it
        self.chords = [frozenset()] * self.n

        if chords:
            chords = sorted(chords, key=lambda c: c[0])
            chord_times = np.asarray([t for t, _ in chords], dtype=np.float64) - start

            # events are rounded, so allow a small tolerance on chord starts
            idx = np.searchsorted(chord_times, self.times + 1e-6, side="right") - 1

            self.chords = [
                frozenset(int(p) % 12 for p in chords[i][1]) if i >= 0 else frozenset()
                for i in idx
            ]

        self._song_position_ids = np.asarray(
            [p for p, _ in song_positions], dtype=np.int32
        )
        self._song_position_times = (
            np.asarray([t for _, t in song_positions], dtype=np.float64) - start
        )

        if any(len(ps) == 0 for ps in self.pitches):
            raise ValueError("Score events must contain at least one pitch.")

    def event_delta(self, a: int, b: int) -> int:
        """Return the number of events from event ``a`` to event ``b``.

        :param a: starting event index.
        :param b: ending event index.
        :return: signed distance in events (negative if ``b`` precedes ``a``).
        """
        return int(b - a)

    def time_delta(self, a: int, b: int) -> float:
        """Return the score time from event ``a`` to event ``b``.

        :param a: starting event index.
        :param b: ending event index.
        :return: signed distance in eighth notes.
        """
        return float(self.times[b] - self.times[a])

    def locate_song_position(self, score_time: float) -> tuple[int, float]:
        """Find the song position marker closest to a score time.

        :param score_time: score time, in eighth notes.
        :return: the marker id and the signed offset from it, in eighth notes.
        :raises ValueError: if the table has no (finite) markers or the time
            is not finite.
        """
        if len(self._song_position_times) == 0:
            raise ValueError("No song positions available.")

        if not np.isfinite(score_time):
            raise ValueError("score_time must be finite.")

        if not np.all(np.isfinite(self._song_position_times)):
            raise ValueError("Song position times must be finite.")

        idx = int(np.argmin(np.abs(self._song_position_times - score_time)))

        return (
            int(self._song_position_ids[idx]),
            float(score_time - self._song_position_times[idx]),
        )


# ============================================================
# NOTE GROUPING
# ============================================================


class NoteGrouper:
    """Groups notes played close together into a single input event."""

    # notes within this many seconds of the first one join its event
    _GROUPING_WINDOW = 0.060

    def __init__(self):
        """Initialise an empty grouper."""
        self._t0 = None
        self._pitches = set()

    def deadline(self) -> float | None:
        """Return the time at which the open group will be complete.

        :return: wall-clock time, or ``None`` if no group is open.
        """
        return None if self._t0 is None else self._t0 + self._GROUPING_WINDOW

    def _emit(self) -> InputEvent:
        """Close the open group and return it as an input event."""
        pc = np.zeros(12, dtype=np.float32)

        for p in self._pitches:
            pc[p % 12] = 1.0

        event = InputEvent(self._t0, pc, max(self._pitches) % 12)

        self._t0 = None
        self._pitches = set()

        return event

    def feed(self, t: float, pitch: int) -> InputEvent | None:
        """Add a note-on to the current group.

        :param t: wall-clock time of the note-on.
        :param pitch: MIDI pitch of the note.
        :return: the previous group if this note is too late to join it.
        """
        out = None

        # the open group expired before this note arrived
        if self._t0 is not None and t > self._t0 + self._GROUPING_WINDOW:
            out = self._emit()

        if self._t0 is None:
            self._t0 = t

        self._pitches.add(pitch)

        return out

    def poll(self, now: float) -> InputEvent | None:
        """Close the open group if its window has elapsed.

        :param now: current wall-clock time.
        :return: the completed group, if any.
        """
        if self._t0 is not None and now >= self._t0 + self._GROUPING_WINDOW:
            return self._emit()

        return None


# ============================================================
# FOLLOWER (VECTORIZED SUBSEQUENCE ALIGNMENT)
# ============================================================


class Follower:
    """Aligns the recent played events to the score.

    The played events are matched to a contiguous stretch of the (looping)
    score by free-start, free-end subsequence alignment, vectorised over all
    score positions.
    """

    # maximum number of played events kept for alignment
    MAX_HISTORY_EVENTS = 32

    # history window length, in eighth notes of the base tempo
    _HISTORY_EIGHTHS = 32
    # minimum number of played events needed to align
    _MIN_HISTORY = 6
    # a silence longer than this (seconds) discards the older history
    _HISTORY_GAP_RESET = 1.0

    # alignment costs for unmatched played / score events
    _INSERTION_COST = 0.30
    _DELETION_COST = 0.35
    # extra insertion cost for the last and second-to-last played events
    _TAIL_INSERTION_EXTRA = (0.30, 0.10)

    # score events closer than this to the best match are not rivals
    _SECOND_BEST_GUARD = 4
    # confidence multiplier for a perfectly ambiguous match
    _MARGIN_FLOOR = 0.60
    # cost gap over which ambiguity fades out
    _MARGIN_SCALE = 1.5

    # alignment may extend this far past the loop end to catch wrap-around
    _MAX_ALIGNMENT_MULTIPLIER = 2
    _MAX_ALIGNMENT_EXTRA = 4

    # pitch-class similarity: kernel width and term weights
    _PITCH_DISTANCE_SIGMA = 0.5
    _PRECISION_SHARE = 0.30

    # soft preference for matches close to the expected position
    _PRIOR_WEIGHT = 0.02
    _PRIOR_SCALE_EVENTS = 64

    def __init__(self, table: EventTable, eighth_seconds: float, melody_weight: float):
        """Precompute the score similarity tables.

        :param table: the score to follow.
        :param eighth_seconds: duration of an eighth note at the base tempo.
        :param melody_weight: weight (0–1) of the melody (top voice) in the
            similarity; the rest goes to the harmony (all other pitches).
        """
        self._table = table
        self._n = table.n

        # BUGFIX: the melody weight was hard-coded to 0.75, ignoring the
        # argument (and so the configuration)
        self._melody_weight = melody_weight
        self._harmony_weight = 1.0 - melody_weight

        n = self._n

        self._history = deque()

        # events older than this many seconds are dropped from the history
        self._base_window = max(1.0, self._HISTORY_EIGHTHS * float(eighth_seconds))

        # circular pitch-class distance, turned into a similarity kernel
        pc = np.arange(12)
        dist = np.abs(pc[:, None] - pc[None, :])
        dist = np.minimum(dist, 12 - dist)

        self._K = np.exp(-0.5 * (dist / self._PITCH_DISTANCE_SIGMA) ** 2).astype(
            np.float32
        )
        K = self._K

        # score pitch-class presence (S) and top pitch class (top) per event
        S = np.zeros((n, 12), dtype=np.float32)
        top = np.zeros(n, dtype=np.intp)

        for i, ps in enumerate(table.pitches):
            for p in ps:
                S[i, p % 12] = 1.0

            top[i] = max(ps) % 12

        inv_c = (1.0 / S.sum(axis=1)).astype(np.float32)

        # B[a, i]: best kernel match of pitch class a among event i's pitches
        B = np.empty((12, n), dtype=np.float32)

        for a in range(12):
            B[a] = (S * K[a][None, :]).max(axis=1)

        # User-defined chords: the played pitches can also be explained by the
        # chord sounding at the event, and the chord can be recalled instead
        # of the notes, since a performer may play the melody, the chords or
        # both. Without chords the tables below are not needed.
        self._has_chords = any(table.chords)

        if self._has_chords:
            Sc = np.zeros((n, 12), dtype=np.float32)

            for i, chord in enumerate(table.chords):
                for p in chord:
                    Sc[i, p] = 1.0

            chord_counts = Sc.sum(axis=1)
            inv_chord = np.divide(
                1.0,
                chord_counts,
                out=np.zeros(n, dtype=np.float32),
                where=chord_counts > 0,
            )

            Bc = np.empty((12, n), dtype=np.float32)

            for a in range(12):
                Bc[a] = (Sc * K[a][None, :]).max(axis=1)

            STc = np.ascontiguousarray(Sc.T)

            # precision is measured against the notes and the chord together
            B = np.maximum(B, Bc)

        TK = np.ascontiguousarray(K[:, top])
        ST = np.ascontiguousarray(S.T)

        # the tables are extended circularly so that matches can wrap around
        self._ext = min(
            n,
            self.MAX_HISTORY_EVENTS * self._MAX_ALIGNMENT_MULTIPLIER
            + self._MAX_ALIGNMENT_EXTRA,
        )

        cols = np.arange(n + self._ext) % n

        self._B_x = np.ascontiguousarray(B[:, cols])
        self._TK_x = np.ascontiguousarray(TK[:, cols])
        self._ST_x = np.ascontiguousarray(ST[:, cols])
        self._inv_x = np.ascontiguousarray(inv_c[cols])

        if self._has_chords:
            self._STc_x = np.ascontiguousarray(STc[:, cols])
            self._invc_x = np.ascontiguousarray(inv_chord[cols])

        # preallocated dynamic programming buffers
        max_c = n + self._ext + 1

        self._D = np.empty((self.MAX_HISTORY_EVENTS + 1, max_c), dtype=np.float64)
        self._tr = np.zeros((self.MAX_HISTORY_EVENTS + 1, max_c), dtype=np.uint8)
        self._tmp = np.empty(max_c, dtype=np.float64)
        self._jdel = np.arange(max_c, dtype=np.float64) * self._DELETION_COST

    # --------------------------------------------------------
    # HISTORY
    # --------------------------------------------------------

    def reset(self):
        """Forget all played events."""
        self._history.clear()

    def ready(self) -> bool:
        """Tell whether enough events were played to attempt an alignment."""
        return len(self._history) >= self._MIN_HISTORY

    def add(self, ev: InputEvent):
        """Append a played event and trim the history.

        :param ev: the new input event.
        """
        h = self._history

        h.append(ev)

        # keep at most MAX_HISTORY_EVENTS events
        while len(h) > self.MAX_HISTORY_EVENTS:
            h.popleft()

        # drop events that are too old, but keep enough to align
        cutoff = ev.timestamp - self._base_window
        keep = self._MIN_HISTORY + 2

        while len(h) > keep and h[0].timestamp < cutoff:
            h.popleft()

        # after a long silence, only the latest phrase is relevant
        for i in range(len(h) - 1, 0, -1):
            if h[i].timestamp - h[i - 1].timestamp > self._HISTORY_GAP_RESET:
                for _ in range(i):
                    h.popleft()

                break

    # --------------------------------------------------------
    # ALIGNMENT
    # --------------------------------------------------------

    def _dp(self, cost):
        """Free-start / free-end subsequence alignment.

        Moves:
            Diagonal: match played event to score event.
            Up:       insert played event.
            Left:     delete score event.

        Left moves are resolved using a vectorised prefix-minimum scan.

        :param cost: matrix of matching costs, played events x score events.
        :return: the accumulated cost matrix and the traceback matrix
            (0 = match, 1 = insertion, 2 = deletion).
        """
        m, columns = cost.shape

        D = self._D[: m + 1, : columns + 1]
        trace = self._tr[: m + 1, : columns + 1]

        deletion_costs = self._jdel[: columns + 1]
        temp = self._tmp[: columns + 1]

        # free alignment start
        D[0, :] = 0.0

        # penalise unmatched played events, especially at the end
        insertion_costs = np.full(m, self._INSERTION_COST)

        for distance, extra_cost in enumerate(self._TAIL_INSERTION_EXTRA):
            if distance < m:
                insertion_costs[m - 1 - distance] += extra_cost

        for i in range(1, m + 1):
            previous = D[i - 1]
            current = D[i]

            insertion = insertion_costs[i - 1]

            # match or insert
            diagonal = previous[:-1] + cost[i - 1]
            inserted = previous[1:] + insertion

            use_insertion = inserted < diagonal

            np.minimum(diagonal, inserted, out=diagonal)

            trace[i, 1:] = use_insertion

            current[0] = previous[0] + insertion
            current[1:] = diagonal

            # resolve score-event deletions using a prefix minimum
            np.subtract(current, deletion_costs, out=temp)
            np.minimum.accumulate(temp, out=temp)
            np.add(temp, deletion_costs, out=current)

            # mark positions where a deletion improved the alignment
            np.putmask(trace[i, 1:], current[1:] < diagonal - 1e-9, 2)

        return D, trace

    def align(self, expected: int | None = None) -> MatchResult | None:
        """Align the played history to the score.

        :param expected: score event the performer is expected to be at. If
            given, matches close to it are slightly preferred.
        :return: the best alignment, or ``None`` if it cannot be computed.
        """
        h = list(self._history)
        m = len(h)

        if m < self._MIN_HISTORY:
            return None

        n = self._n

        # number of (circularly extended) score columns
        C = n + self._ext

        B = self._B_x
        TK = self._TK_x
        ST = self._ST_x
        inv = self._inv_x

        # played pitch classes (O) and top pitch classes
        O = np.stack([e.pc for e in h])
        top = np.fromiter((e.top_pc for e in h), dtype=np.intp, count=m)

        co = O.sum(axis=1)
        Bo = (O[:, :, None] * self._K[None, :, :]).max(axis=1)

        # precision: how well played pitches are explained by the score event
        P = (O @ B) / co[:, None]

        # recall: how well the score event's pitches are found in the played one
        R = (Bo @ ST) * inv[None, :]

        # with user-defined chords, recalling the chord is as good
        if self._has_chords:
            R = np.maximum(R, (Bo @ self._STc_x) * self._invc_x[None, :])

        # melody: how well the top voices agree
        M = TK[top]

        sim = (
            (self._harmony_weight * self._PRECISION_SHARE) * P
            + (self._harmony_weight * (1.0 - self._PRECISION_SHARE)) * R
            + self._melody_weight * M
        )

        cost = 1.0 - sim

        D, tr = self._dp(cost)

        # average alignment cost for every possible end column
        raw = D[m, 1 : C + 1] / m

        s_idx = np.arange(C)

        # prefer matches near the expected position, if there is one
        selection = raw

        if expected is not None:
            d = np.abs(s_idx - expected)

            selection = raw + self._PRIOR_WEIGHT * np.minimum(
                d / self._PRIOR_SCALE_EVENTS, 1.0
            )

        c_best = int(np.argmin(selection))
        best_cost = float(raw[c_best])

        # ----------------------------------------------------
        # TRACEBACK
        # ----------------------------------------------------

        played_idx = []
        score_idx = []

        i = m
        j = c_best + 1

        while i > 0:
            if j == 0:
                i -= 1
                continue

            op = tr[i, j]

            if op == 2:
                # a score event was skipped
                j -= 1

            elif op == 1:
                # a played event was extra
                i -= 1

            else:
                # played event i-1 matches score event j-1
                played_idx.append(i - 1)
                score_idx.append(j - 1)

                i -= 1
                j -= 1

        if not played_idx:
            return None

        played_idx.reverse()
        score_idx.reverse()

        # the position is where the last matched played event landed
        position = int(score_idx[-1] % n)

        score_time = float(self._table.times[position])

        song_position, song_offset = self._table.locate_song_position(score_time)

        matched = len(played_idx)

        # ----------------------------------------------------
        # CONFIDENCE
        # ----------------------------------------------------

        confidence = math.exp(-2.0 * best_cost) * (matched / m)

        # ----------------------------------------------------
        # AMBIGUITY
        # ----------------------------------------------------

        # best cost among far away rivals of the chosen position
        rival = np.abs(s_idx - c_best) > self._SECOND_BEST_GUARD

        if rival.any():
            second = float(raw[rival].min())

            gap = max(second - best_cost, 0.0) * m

            margin_factor = self._MARGIN_FLOOR + (1.0 - self._MARGIN_FLOOR) * (
                1.0 - math.exp(-gap / self._MARGIN_SCALE)
            )

            confidence *= margin_factor

        return MatchResult(
            position=position,
            score_time=score_time,
            song_position=song_position,
            song_offset=song_offset,
            confidence=confidence,
            timestamp=float(h[played_idx[-1]].timestamp),
        )


# ============================================================
# ACQUISITION EVIDENCE
# ============================================================


class Tracker:
    """Collects confident results forming a coherent trajectory."""

    # a trajectory may move this many events backwards...
    _CONSIST_BACK = 4
    # ...and this many events forward per new played event, plus a slack
    _CONSIST_FWD_PER_EVENT = 4
    _CONSIST_SLACK = 4

    # evidence older than this (in eighths of score time or seconds) is dropped
    _EVIDENCE_WINDOW = 4.0
    _EVIDENCE_MAX_AGE = 3.0

    # minimum evidence to consider the trajectory reliable
    _MIN_EVIDENCE_MATCHES = 3
    _MIN_EVIDENCE_SPAN = 1.5

    def __init__(self, table: EventTable):
        """Initialise an empty tracker.

        :param table: the score being followed.
        """
        self._table = table
        self._evidence = deque()

    def reset(self):
        """Discard all collected evidence."""
        self._evidence.clear()

    def is_consistent(self, delta: int, new_events: int) -> bool:
        """Tell whether a jump in score position is a plausible continuation.

        :param delta: signed distance in score events.
        :param new_events: played events since the previous position.
        """
        max_forward = self._CONSIST_FWD_PER_EVENT * max(new_events, 1)

        return -self._CONSIST_BACK <= delta <= max_forward + self._CONSIST_SLACK

    def add(self, result: MatchResult, new_events: int):
        """Add a confident result to the evidence.

        Evidence that does not form a trajectory with the new result is
        discarded.

        :param result: the new alignment result.
        :param new_events: played events since the previous result.
        """
        beat = 0.0

        if self._evidence:
            previous = self._evidence[-1]

            event_delta = self._table.event_delta(previous.position, result.position)

            if self.is_consistent(event_delta, new_events):
                # advance the score time along the trajectory
                beat = previous.beat + self._table.time_delta(
                    previous.position, result.position
                )
            else:
                self._evidence.clear()

        self._evidence.append(
            Evidence(
                timestamp=result.timestamp,
                beat=beat,
                confidence=result.confidence,
                position=result.position,
            )
        )

        # drop evidence that fell out of the time or score window
        while len(self._evidence) > 1:
            oldest = self._evidence[0]

            outside_window = oldest.beat < beat - self._EVIDENCE_WINDOW
            too_old = result.timestamp - oldest.timestamp > self._EVIDENCE_MAX_AGE

            if not outside_window and not too_old:
                break

            self._evidence.popleft()

    def summary(self) -> tuple[float, int, float]:
        """Summarise the collected evidence.

        :return: mean confidence, number of matches and span in eighth notes.
        """
        if not self._evidence:
            return 0.0, 0, 0.0

        confidences = [e.confidence for e in self._evidence]

        return (
            float(np.mean(confidences)),
            len(self._evidence),
            self._evidence[-1].beat - self._evidence[0].beat,
        )

    def is_reliable(self, needed: int, threshold: float) -> bool:
        """Tell whether the evidence is enough to acquire the position.

        :param needed: number of matches required (at least a minimum).
        :param threshold: minimum mean confidence.
        """
        confidence, count, span = self.summary()

        return (
            count >= max(needed, self._MIN_EVIDENCE_MATCHES)
            and span >= self._MIN_EVIDENCE_SPAN
            and confidence >= threshold
        )


# ============================================================
# ENGINE
# ============================================================


class TrackerEngine:
    """Single-threaded tracker engine.

    Drive it from ONE worker thread: feed it notes, poll it for completed
    groups and process the resulting events.
    """

    # while acquired, results above this fraction of the threshold keep the
    # position alive (hysteresis)
    _HOLD_FRACTION = 0.75

    def __init__(
        self,
        table: EventTable,
        eighth_seconds: float,
        threshold: float,
        confirmations: int,
        collection_seconds: float,
        melody_vs_harmony_weight: float,
        on_acquire=None,
        on_jump=None,
        on_match=None,
        log=print,
    ):
        """Initialise the engine.

        :param table: the score to follow.
        :param eighth_seconds: duration of an eighth note at the base tempo.
        :param threshold: minimum confidence to trust an alignment.
        :param confirmations: consistent results needed to acquire a position
            or to accept a jump away from it.
        :param collection_seconds: minimum listening time before acquiring.
        :param melody_vs_harmony_weight: weight (0–1) of the melody (top voice)
            against the harmony (all other pitches and the chords of the
            tune) when comparing played and written notes.
        :param on_acquire: called with the :class:`MatchResult` on acquisition.
        :param on_jump: called with the :class:`MatchResult` on a position jump.
        :param on_match: called with the :class:`MatchResult` every time the
            tracked position is updated while acquired (including the
            acquisition and jumps), to follow the performer's progress.
        :param log: function used to report acquisitions and jumps.
        """
        self._table = table

        self._follower = Follower(table, eighth_seconds, melody_vs_harmony_weight)
        self._tracker = Tracker(table)
        self._grouper = NoteGrouper()

        self._threshold = threshold
        self._confirmations = max(1, confirmations)
        self._collection_seconds = collection_seconds

        self._on_acquire = on_acquire
        self._on_jump = on_jump
        self._on_match = on_match
        self._log = log

        self._state = TrackerState("SEARCHING")

        # wall-clock time of the first played event
        self._first_timestamp = None
        # played events since the position was last updated
        self._events_since_update = 0
        # candidate jump target as [position, confirmations]
        self._alt = None

    @property
    def state(self) -> TrackerState:
        """The current tracker state."""
        return self._state

    # --------------------------------------------------------
    # RESET
    # --------------------------------------------------------

    def reset(self):
        """Forget everything and go back to searching."""
        self._follower.reset()
        self._tracker.reset()

        self._grouper = NoteGrouper()

        self._state = TrackerState("SEARCHING")

        self._first_timestamp = None
        self._events_since_update = 0

        self._alt = None

    # --------------------------------------------------------
    # INPUT SIDE
    # --------------------------------------------------------

    def feed(self, t: float, pitch: int) -> list[InputEvent]:
        """Feed a note-on to the grouper.

        :param t: wall-clock time of the note-on.
        :param pitch: MIDI pitch of the note.
        :return: the input events completed by this note.
        """
        ev = self._grouper.feed(t, pitch)

        return [ev] if ev is not None else []

    def poll(self, now: float) -> list[InputEvent]:
        """Collect the input events that completed with the passage of time.

        :param now: current wall-clock time.
        :return: the completed input events.
        """
        ev = self._grouper.poll(now)

        return [ev] if ev is not None else []

    def deadline(self) -> float | None:
        """Return the wall-clock time at which :meth:`poll` should be called.

        :return: the time, or ``None`` if no event is pending.
        """
        return self._grouper.deadline()

    # --------------------------------------------------------
    # STATE ACCEPTANCE
    # --------------------------------------------------------

    def _accept(self, result: MatchResult):
        """Adopt a result as the current position.

        :param result: the result to adopt.
        """
        self._state.result = result

        self._events_since_update = 0
        self._alt = None

        if self._on_match is not None:
            self._on_match(result)

    # --------------------------------------------------------
    # ACQUIRED POSITION UPDATE
    # --------------------------------------------------------

    def _update_acquired(self, result: MatchResult, new_events: int):
        """Update the position once acquired.

        Results that continue the trajectory are accepted; results that jump
        elsewhere must be confirmed by several consistent results first.

        :param result: the new alignment result.
        :param new_events: played events that led to this result.
        """
        self._events_since_update = min(
            self._events_since_update + new_events,
            Follower.MAX_HISTORY_EVENTS,
        )

        d = self._table.event_delta(self._state.result.position, result.position)

        # a continuation of the current trajectory
        if self._tracker.is_consistent(d, self._events_since_update):
            if result.confidence >= self._HOLD_FRACTION * self._threshold:
                self._accept(result)

            return

        # a jump: ignore it unless it is confident...
        if result.confidence < self._threshold:
            return

        # ...and repeatedly confirmed by consistent results
        alt = self._alt

        if alt is not None and self._tracker.is_consistent(
            self._table.event_delta(alt[0], result.position), new_events
        ):
            alt[0] = result.position
            alt[1] += 1

        else:
            self._alt = alt = [result.position, 1]

        if alt[1] >= self._confirmations:
            self._log(
                f"POSITION JUMP: "
                f"song_position={self._state.result.song_position} -> "
                f"{result.song_position} "
                f"(offset={result.song_offset:+.2f} eighths, "
                f"confidence={result.confidence:.3f})"
            )

            self._accept(result)

            if self._on_jump is not None:
                self._on_jump(result)

    # --------------------------------------------------------
    # MAIN PROCESSING
    # --------------------------------------------------------

    def process(self, events: list[InputEvent]) -> MatchResult | None:
        """Consume completed input events and update the tracked position.

        :param events: completed input events, oldest first.
        :return: the latest alignment, or ``None`` if none was computed.
        """
        if not events:
            return None

        for ev in events:
            if self._first_timestamp is None:
                self._first_timestamp = ev.timestamp

            self._follower.add(ev)

        if not self._follower.ready():
            return None

        acquired = self._state.mode == "ACQUIRED"

        expected = self._state.result.position if acquired else None
        result = self._follower.align(expected)

        if result is None:
            return None

        if acquired:
            self._update_acquired(result, len(events))

            return result

        # still searching: only confident results count as evidence
        if result.confidence < self._threshold:
            return result

        self._tracker.add(result, len(events))

        if not self._tracker.is_reliable(self._confirmations, self._threshold):
            return result

        # listen for a minimum time before committing to a position
        if result.timestamp - self._first_timestamp < self._collection_seconds:
            return result

        conf, count, span = self._tracker.summary()

        self._log(
            f"ACQUISITION: "
            f"song_position={result.song_position} "
            f"(offset={result.song_offset:+.2f} eighths, "
            f"score_time={result.score_time:.2f}), "
            f"event={result.position}, "
            f"confidence={conf:.3f}, "
            f"matches={count}, "
            f"span={span:.2f} eighths"
        )

        self._state = TrackerState(mode="ACQUIRED", result=result)

        if self._on_acquire is not None:
            self._on_acquire(result)

        if self._on_match is not None:
            self._on_match(result)

        return result
