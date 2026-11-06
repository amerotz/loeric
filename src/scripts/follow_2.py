#!/usr/bin/env python3

"""Real-time MIDI score follower / accompanist.

    python score_follower.py --list-ports
    python score_follower.py piece.musicxml --input "My Keyboard" --output "My Synth"
    python score_follower.py --selftest            # no MIDI hardware needed

You play; the program listens, works out where you are in the score (even if you
start in the middle, play wrong/missing notes, change tempo or jump somewhere
else) and plays the score on the output port, phase-locked to you.

Requirements:  pip install numpy mido python-rtmidi music21
Python 3.9+.

Design summary
--------------
* MIDI input uses rtmidi's callback (no polling); chord grouping happens in the
  main loop with proper timeouts (the original blocked until the NEXT note).
* Position finding is a full subsequence alignment of the recent notes against
  the whole (circular) score, vectorised in numpy: ~1-3 ms for a 5000-event
  score. Deletions are handled correctly (prefix-min scan), notes can be
  missing, extra or wrong, and the piece may be entered anywhere.
* Once locked, a prior toward the expected position removes flips between
  repeated passages; huge scores use a local window + periodic global checks.
* Playback is a single persistent thread with a lock-free clock snapshot,
  hybrid sleep/spin timing, tempo following AND phase correction, and hard
  re-seeking on confirmed jumps.
* Every note-on that is sent has a guaranteed note-off (plus CC123 panic).
"""

import argparse
import gc
import heapq
import math
import queue
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass

import mido
import numpy as np

# ============================================================
# CONFIGURATION
# ============================================================

GROUPING_WINDOW = 0.060  # seconds: notes this close form one chord event
STARTUP_COLLECTION_SECONDS = 2.0  # minimum listening time before first lock

# Rolling history of played events.
HISTORY_BARS = 2
MIN_HISTORY = 6
MAX_HISTORY_EVENTS = 32
HISTORY_GAP_RESET = 1.0  # a silence this long discards older history

CONFIDENCE_THRESHOLD = 0.68

# Alignment costs (per event, normalised cost range 0..1 for a bad match).
INSERTION_COST = 0.30  # you played something the score doesn't have
DELETION_COST = 0.35  # you skipped a score event
MAX_ALIGNMENT_MULTIPLIER = 2
MAX_ALIGNMENT_EXTRA = 4
SECOND_BEST_GUARD = 1  # events; rival alignment must be further away

# Perceptual matching (pitch-class based).
PITCH_DISTANCE_SIGMA = (
    1.0  # semitones; a wrong note a semitone off still scores partially
)
MELODY_WEIGHT = 0.25  # top voice
HARMONY_WEIGHT = 0.75  # whole-chord pitch-class agreement
PRECISION_SHARE = (
    0.70  # inside HARMONY: "your notes are in the chord" vs "chord notes were played"
)

RHYTHM_WEIGHT = 0.20
RHYTHM_SIGMA = 0.35  # seconds of timing residual that costs ~63% of rhythm score
MIN_SLOPE_SPAN = 0.30  # seconds between events used for tempo estimation

# Position prior while locked.
PRIOR_WEIGHT = 0.08
PRIOR_SCALE_EVENTS = 64

# Acquisition (metrical evidence).
EVIDENCE_WINDOW_BEATS = 1.0
MIN_EVIDENCE_MATCHES = 3
MIN_EVIDENCE_SPAN_BEATS = 0.75
EVIDENCE_MAX_AGE = 8.0
CONSIST_BACK = 3  # events a result may move backwards and still be "the same place"
CONSIST_FWD_PER_EVENT = 4
CONSIST_SLACK = 4

# Phase / tempo control while playing.
RESYNC_SECONDS = 0.60  # beyond this we treat a result as disagreeing with playback
SYNC_DEADBAND = 0.012
SYNC_GAIN = 0.35
TEMPO_HISTORY_SIZE = 20
TEMPO_SMOOTHING = 0.20
MIN_PLAYBACK_SPEED = 0.5
MAX_PLAYBACK_SPEED = 2.5
SPEED_UPDATE_INTERVAL = 0.10

# Playback.
MIDI_VELOCITY = 85
MIN_NOTE_SECONDS = 0.03
MAX_LATE_SECONDS = (
    0.12  # events later than this are dropped instead of played in a burst
)
SPIN_SECONDS = 0.0015  # final stretch before an event is spin-waited for precision

# Huge scores: local alignment window + periodic global check.
WINDOWED_SCORE_EVENTS = 8000
LOCAL_HALF_WINDOW = 1500
GLOBAL_CHECK_EVERY = 8

IDLE_TICK = 0.10
VERBOSE = False


# ============================================================
# DATA STRUCTURES
# ============================================================


@dataclass
class ScoreEvent:
    position: float  # quarter-note offset
    duration: float  # longest note, in quarter notes
    pitches: frozenset
    notes: tuple  # ((midi, duration_in_quarters), ...)


@dataclass
class InputEvent:
    timestamp: float
    pitches: frozenset
    pc: np.ndarray  # 12-vector of pitch classes present
    top_pc: int


@dataclass
class MatchResult:
    position: int  # score event index of the last matched played event
    confidence: float
    cost: float
    matched_events: int
    tempo_ratio: object  # score-seconds per wall-second, or None if unknown
    rhythm_score: float
    timestamp: float  # wall time of the played event matched to `position`
    n_observed: int


@dataclass
class Evidence:
    timestamp: float
    beat: float
    confidence: float
    position: int


# ============================================================
# SCORE LOADING
# ============================================================


class Score:

    def __init__(self, filename):
        self.filename = filename
        self.bar_positions = []
        self.bar_duration = 4.0
        self._load(filename)

    # ---------------------------------------------------- loading

    @staticmethod
    def _expand_repeats(parsed, stream):
        def expand(part):
            measured = part
            if not list(measured.getElementsByClass(stream.Measure)):
                measured = measured.makeMeasures()
            try:
                return measured.expandRepeats()
            except Exception as exc:
                print("Repeat expansion warning:", exc)
                return measured

        if getattr(parsed, "parts", None) and len(parsed.parts):
            result = stream.Score()
            for part in parsed.parts:
                result.insert(0, expand(part))
            return result
        return expand(parsed)

    def _load(self, filename):
        from music21 import chord, converter, harmony, note, stream, tempo

        print("Loading:", filename)
        parsed = converter.parse(filename)
        expanded = self._expand_repeats(parsed, stream)
        flat = expanded.flatten()

        # ---- tempo map (note: flatten() drops Measure objects, so bars
        # must be read from the un-flattened stream).
        marks = {}
        for mark in flat.getElementsByClass(tempo.MetronomeMark):
            bpm = None
            try:
                bpm = mark.getQuarterBPM()
            except Exception:
                pass
            if not bpm:
                bpm = mark.number
            if bpm and bpm > 0:
                marks[round(float(mark.offset), 6)] = float(min(max(bpm, 10.0), 600.0))
        tempos = sorted(marks.items())
        if not tempos:
            tempos = [(0.0, 120.0)]
        elif tempos[0][0] > 0:
            tempos.insert(0, (0.0, tempos[0][1]))
        self.tempos = tempos
        self._tp = np.asarray([t[0] for t in tempos], dtype=np.float64)
        self._tbpm = np.asarray([t[1] for t in tempos], dtype=np.float64)
        cum = np.zeros(len(tempos))
        for i in range(1, len(tempos)):
            cum[i] = (
                cum[i - 1] + (self._tp[i] - self._tp[i - 1]) * 60.0 / self._tbpm[i - 1]
            )
        self._tcum = cum

        # ---- bars
        offsets = set()
        try:
            for m in expanded.recurse().getElementsByClass(stream.Measure):
                offsets.add(round(float(m.getOffsetInHierarchy(expanded)), 6))
        except Exception:
            pass
        self.bar_positions = sorted(offsets)
        if len(self.bar_positions) > 1:
            diffs = np.diff(self.bar_positions)
            diffs = diffs[diffs > 0]
            if len(diffs):
                self.bar_duration = float(np.median(diffs))

        # ---- notes (ties merged so that tied notes are ONE onset)
        raw = []
        for el in flat.notes:
            if isinstance(el, harmony.Harmony):
                continue  # chord symbols are not played notes
            off = round(float(el.offset), 6)
            q = max(float(el.duration.quarterLength), 0.0)
            if isinstance(el, note.Note):
                raw.append(
                    (off, int(el.pitch.midi), q, el.tie.type if el.tie else None)
                )
            elif isinstance(el, chord.Chord):
                for n in el.notes:
                    tie = n.tie if n.tie is not None else el.tie
                    raw.append((off, int(n.pitch.midi), q, tie.type if tie else None))
        raw.sort(key=lambda r: (r[0], r[1]))

        onsets = {}  # (offset, midi) -> end offset
        open_ties = {}  # midi -> key of the onset the tie continues
        for off, midi, q, tie in raw:
            midi = min(max(midi, 0), 127)
            end = off + q
            if tie in ("continue", "stop"):
                key = open_ties.get(midi)
                if key is not None and abs(onsets[key] - off) < 0.02:
                    onsets[key] = max(onsets[key], end)
                    if tie == "stop":
                        del open_ties[midi]
                    continue
            key = (off, midi)
            onsets[key] = max(onsets.get(key, 0.0), end)
            if tie in ("start", "continue"):
                open_ties[midi] = key
            else:
                open_ties.pop(midi, None)

        grouped = {}
        for (off, midi), end in onsets.items():
            grouped.setdefault(off, {})[midi] = end

        self.events = []
        for pos in sorted(grouped):
            d = grouped[pos]
            notes = tuple(sorted((m, max(e - pos, 0.0)) for m, e in d.items()))
            self.events.append(
                ScoreEvent(pos, max(x[1] for x in notes), frozenset(d), notes)
            )
        if not self.events:
            raise ValueError("No playable notes found.")

        # ---- precomputed arrays
        self.n = len(self.events)
        self.positions = np.asarray([e.position for e in self.events], dtype=np.float64)
        self.loop_start = float(self.positions[0])
        start_sec = float(self.seconds(self.loop_start))
        self.event_times = np.maximum.accumulate(
            self.seconds(self.positions) - start_sec
        )
        self.event_beats = self.positions - self.loop_start

        loop_end = max(e.position + e.duration for e in self.events)
        self.loop_beats = float(loop_end - self.loop_start)
        self.loop_duration = float(self.seconds(loop_end)) - start_sec
        self.loop_duration = max(self.loop_duration, float(self.event_times[-1]) + 0.05)
        if self.loop_duration <= 0 or self.loop_beats <= 0:
            raise ValueError("Invalid score duration.")
        self.loop_beats = max(self.loop_beats, float(self.event_beats[-1]) + 1e-3)

        flat_pos, flat_dur, owner = [], [], []
        for i, e in enumerate(self.events):
            for _, d in e.notes:
                flat_pos.append(e.position)
                flat_dur.append(d)
                owner.append(i)
        flat_pos = np.asarray(flat_pos)
        flat_dur = np.asarray(flat_dur)
        secs = np.maximum(
            self.seconds(flat_pos + flat_dur) - self.seconds(flat_pos), MIN_NOTE_SECONDS
        )
        self.event_notes = []
        k = 0
        for e in self.events:
            items = []
            for m, _ in e.notes:
                items.append((m, float(secs[k])))
                k += 1
            self.event_notes.append(tuple(items))

        self.event_times.setflags(write=False)
        self.event_beats.setflags(write=False)

        sec_per_beat = self.loop_duration / self.loop_beats
        self._history_window = max(1.0, HISTORY_BARS * self.bar_duration * sec_per_beat)

        print("Score events:", self.n)
        print("Score bars:", len(self.bar_positions))
        print("Average bar duration (beats):", round(self.bar_duration, 3))
        print("Loop duration (s):", round(self.loop_duration, 2))

    # ---------------------------------------------------- helpers

    def seconds(self, position):
        """Quarter-note offset(s) -> seconds under the tempo map (vectorised)."""
        pos = np.asarray(position, dtype=np.float64)
        idx = np.clip(
            np.searchsorted(self._tp, pos, side="right") - 1, 0, len(self._tp) - 1
        )
        return self._tcum[idx] + (pos - self._tp[idx]) * 60.0 / self._tbpm[idx]

    def time_for_index(self, g):
        """Absolute score time of (possibly cycle-extended) event index g."""
        g = np.asarray(g)
        return (g // self.n) * self.loop_duration + self.event_times[g % self.n]

    def event_delta(self, a, b):
        """Signed circular distance b - a in events."""
        n = self.n
        return int((b - a + n // 2) % n - n // 2)

    def beat_delta(self, a, b):
        Lb = self.loop_beats
        return float((self.event_beats[b] - self.event_beats[a] + Lb / 2) % Lb - Lb / 2)

    def beat_distance(self, a, b):
        return abs(self.beat_delta(a, b))

    def wrap_time(self, x):
        L = self.loop_duration
        return (x + L / 2) % L - L / 2

    def history_window_seconds(self):
        return self._history_window


# ============================================================
# MIDI INPUT
# ============================================================


class MIDIInput:
    """rtmidi callback -> lock-free queue of (perf_counter timestamp, pitch)."""

    def __init__(self, port_name):
        self.port_name = port_name
        self.queue = queue.SimpleQueue()
        self.port = None

    def _callback(self, message):
        if message.type == "note_on" and message.velocity > 0:
            self.queue.put((time.perf_counter(), message.note))

    def start(self):
        print("Opening MIDI input:", self.port_name)
        self.port = mido.open_input(self.port_name, callback=self._callback)

    def stop(self):
        if self.port is not None:
            try:
                self.port.close()
            except Exception:
                pass
            self.port = None


class NoteGrouper:
    """Groups notes within GROUPING_WINDOW of the first one into a single event."""

    def __init__(self, window):
        self.window = window
        self.t0 = None
        self.pitches = set()

    def deadline(self):
        return None if self.t0 is None else self.t0 + self.window

    def _make_input_event(self):
        pc = np.zeros(12, dtype=np.float32)
        for p in self.pitches:
            pc[p % 12] = 1.0
        return InputEvent(self.t0, frozenset(self.pitches), pc, max(self.pitches) % 12)

    def _emit(self):
        ev = self._make_input_event()
        self.t0 = None
        self.pitches = set()
        return ev

    def feed(self, t, pitch):
        out = None
        if self.t0 is not None and t > self.t0 + self.window:
            out = self._emit()
        if self.t0 is None:
            self.t0 = t
        self.pitches.add(pitch)
        return out

    def poll(self, now):
        if self.t0 is not None and now >= self.t0 + self.window:
            return self._emit()
        return None


# ============================================================
# SCORE FOLLOWER (vectorised subsequence alignment)
# ============================================================


class ScoreFollower:

    def __init__(self, score):
        self.score = score
        score_length = self.score_length = score.n
        self.history = deque()
        self.base_window = score.history_window_seconds()
        self.speed_hint = 1.0

        # precalculate pitch class kernel distances
        pitch_classes = np.arange(12)
        dist = np.abs(pitch_classes[:, None] - pitch_classes[None, :])
        dist = np.minimum(dist, 12 - dist)
        pitch_class_kernel = np.exp(-0.5 * (dist / PITCH_DISTANCE_SIGMA) ** 2).astype(
            np.float32
        )
        self.pitch_class_kernel = pitch_class_kernel

        # precompute the inverse of the number of
        # pitch classes per score position
        score_matrix = np.zeros((score_length, 12), dtype=np.float32)
        score_top_voice = np.zeros(score_length, dtype=np.intp)
        for i, e in enumerate(score.events):
            for p in e.pitches:
                score_matrix[i, p % 12] = 1.0
            score_top_voice[i] = max(e.pitches) % 12
        inverse_pitch_class_count = (1.0 / score_matrix.sum(axis=1)).astype(np.float32)

        # precompute the matrix of which pitch class
        # would match a given score event best
        # best_pitch_to_event_match[a, j] = best kernel match of pitch class `a` against score event j.
        best_pitch_to_event_match = np.empty((12, score_length), dtype=np.float32)
        for a in range(12):
            best_pitch_to_event_match[a] = (
                score_matrix * pitch_class_kernel[a][None, :]
            ).max(axis=1)

        # topline_pitch_class_kernel[a, j] = K[a, top_j]
        # pitch class kernel for top voice only
        topline_pitch_class_kernel = np.ascontiguousarray(
            pitch_class_kernel[:, score_top_voice]
        )
        score_matrix_T = np.ascontiguousarray(score_matrix.T)
        (
            self.best_pitch_to_event_match,
            self.topline_pitch_class_kernel,
            self.score_matrix_T,
            self.inverse_pitch_class_count,
        ) = (
            best_pitch_to_event_match,
            topline_pitch_class_kernel,
            score_matrix_T,
            inverse_pitch_class_count,
        )

        # Circularly extended copies so a match may wrap past the end of the score.
        self.circular_extension_amount = min(
            score_length,
            MAX_HISTORY_EVENTS * MAX_ALIGNMENT_MULTIPLIER + MAX_ALIGNMENT_EXTRA,
        )
        cols = np.arange(score_length + self.circular_extension_amount) % score_length
        self.best_pitch_to_event_match_x = np.ascontiguousarray(
            best_pitch_to_event_match[:, cols]
        )
        self.topline_pitch_class_kernel_x = np.ascontiguousarray(
            topline_pitch_class_kernel[:, cols]
        )
        self.score_matrix_T_x = np.ascontiguousarray(score_matrix_T[:, cols])
        self.inverse_pitch_class_count_x = np.ascontiguousarray(
            inverse_pitch_class_count[cols]
        )

        # preallocate dynamic programming matrices
        max_c = (
            max(
                score_length + self.circular_extension_amount, 2 * LOCAL_HALF_WINDOW + 1
            )
            + 1
        )
        self._D = np.empty((MAX_HISTORY_EVENTS + 1, max_c), dtype=np.float64)
        self._tr = np.zeros((MAX_HISTORY_EVENTS + 1, max_c), dtype=np.uint8)
        self._tmp = np.empty(max_c, dtype=np.float64)
        self._jdel = np.arange(max_c, dtype=np.float64) * DELETION_COST

    # ---------------------------------------------------- history

    def reset(self):
        self.history.clear()

    def ready(self):
        return len(self.history) >= MIN_HISTORY

    def add(self, ev):
        h = self.history
        h.append(ev)
        while len(h) > MAX_HISTORY_EVENTS:
            h.popleft()
        speed = min(max(self.speed_hint, MIN_PLAYBACK_SPEED), MAX_PLAYBACK_SPEED)
        cutoff = ev.timestamp - self.base_window / speed
        keep = MIN_HISTORY + 2
        while len(h) > keep and h[0].timestamp < cutoff:
            h.popleft()
        for i in range(len(h) - 1, 0, -1):
            if h[i].timestamp - h[i - 1].timestamp > HISTORY_GAP_RESET:
                for _ in range(i):
                    h.popleft()
                break

    # ---------------------------------------------------- alignment core

    def _dp(self, cost):
        """Free-start / free-end subsequence alignment.

        D[i, j]: best cost of aligning the first i played events to a score
        segment ending at column j. Moves: match (diag), played-event
        insertion (up), score-event deletion (left). The left moves are
        resolved for a whole row at once with a prefix-minimum scan.
        """
        m, C = cost.shape
        D = self._D[: m + 1, : C + 1]
        tr = self._tr[: m + 1, : C + 1]
        jdel = self._jdel[: C + 1]
        tmp = self._tmp[: C + 1]
        D[0, :] = 0.0
        for i in range(1, m + 1):
            prev = D[i - 1]
            row = D[i]
            diag = prev[:-1] + cost[i - 1]
            ins = prev[1:] + INSERTION_COST
            use_ins = ins < diag
            np.minimum(diag, ins, out=diag)
            tr[i, 1:] = use_ins
            row[0] = prev[0] + INSERTION_COST
            row[1:] = diag
            np.subtract(row, jdel, out=tmp)
            np.minimum.accumulate(tmp, out=tmp)
            np.add(tmp, jdel, out=row)
            np.putmask(tr[i, 1:], row[1:] < diag - 1e-9, 2)
        return D, tr

    @staticmethod
    def _rhythm(t_in, t_sc):
        """Robust tempo (score s / wall s) and timing consistency of matched pairs."""
        k = len(t_in)
        if k < 4:
            return None, 0.5
        iu = np.triu_indices(k, 1)
        dt = (t_in[None, :] - t_in[:, None])[iu]
        ds = (t_sc[None, :] - t_sc[:, None])[iu]
        ok = (dt >= MIN_SLOPE_SPAN) & (ds > 0)
        if ok.sum() < 2:
            return None, 0.5
        slopes = ds[ok] / dt[ok]
        slopes = slopes[(slopes >= MIN_PLAYBACK_SPEED) & (slopes <= MAX_PLAYBACK_SPEED)]
        if len(slopes) < 2:
            return None, 0.3
        speed = float(np.median(slopes))
        resid = t_sc - speed * t_in
        resid = np.abs(resid - np.median(resid))
        return speed, float(math.exp(-float(np.median(resid)) / RHYTHM_SIGMA))

    def align(self, expected=None, windowed=False):
        history = list(self.history)
        history_length = len(history)
        if history_length < MIN_HISTORY:
            return None
        score_length = self.score_length

        if (
            windowed
            and expected is not None
            and score_length
            > 2 * LOCAL_HALF_WINDOW + 1 + self.circular_extension_amount
        ):
            start = (expected - LOCAL_HALF_WINDOW) % score_length
            extended_score_length = 2 * LOCAL_HALF_WINDOW + 1
            idx = (start + np.arange(extended_score_length)) % score_length
            (
                best_pitch_to_event_match,
                topline_pitch_class_kernel,
                score_matrix_T,
                inverse_pitch_class_count,
            ) = (
                self.best_pitch_to_event_match[:, idx],
                self.topline_pitch_class_kernel[:, idx],
                self.score_matrix_T[:, idx],
                self.inverse_pitch_class_count[idx],
            )
        else:
            start = 0
            extended_score_length = score_length + self.circular_extension_amount
            (
                best_pitch_to_event_match,
                topline_pitch_class_kernel,
                score_matrix_T,
                inverse_pitch_class_count,
            ) = (
                self.best_pitch_to_event_match_x,
                self.topline_pitch_class_kernel_x,
                self.score_matrix_T_x,
                self.inverse_pitch_class_count_x,
            )

        observed_pitch_classes = np.stack([e.pc for e in history])
        observed_pitch_classes_topline = np.fromiter(
            (e.top_pc for e in history), dtype=np.intp, count=history_length
        )
        co = observed_pitch_classes.sum(axis=1)
        best_pitch_to_event_match_observed = (
            observed_pitch_classes[:, :, None] * self.pitch_class_kernel[None, :, :]
        ).max(axis=1)
        P = (observed_pitch_classes @ best_pitch_to_event_match) / co[
            :, None
        ]  # played notes explained by the score chord
        R = (
            best_pitch_to_event_match_observed @ score_matrix_T
        ) * inverse_pitch_class_count[
            None, :
        ]  # score chord notes that were played
        M = topline_pitch_class_kernel[
            observed_pitch_classes_topline
        ]  # top voice agreement
        sim = (
            (HARMONY_WEIGHT * PRECISION_SHARE) * P
            + (HARMONY_WEIGHT * (1.0 - PRECISION_SHARE)) * R
            + MELODY_WEIGHT * M
        )
        cost = 1.0 - sim

        D, tr = self._dp(cost)
        raw = (
            D[history_length, 1 : extended_score_length + 1] / history_length
        )  # normalised cost for each end column
        cols = np.arange(extended_score_length)
        s_idx = (start + cols) % score_length

        selection = raw
        if expected is not None:
            d = np.abs(s_idx - expected)
            d = np.minimum(d, score_length - d)
            selection = raw + PRIOR_WEIGHT * np.minimum(d / PRIOR_SCALE_EVENTS, 1.0)
        c_best = int(np.argmin(selection))
        best_cost = float(raw[c_best])

        # ---- traceback
        po, pc_ = [], []
        i, j = history_length, c_best + 1
        while i > 0:
            if j == 0:
                i -= 1
                continue
            op = tr[i, j]
            if op == 2:
                j -= 1
            elif op == 1:
                i -= 1
            else:
                po.append(i - 1)
                pc_.append(j - 1)
                i -= 1
                j -= 1
        if not po:
            return None
        po.reverse()
        pc_.reverse()
        po = np.asarray(po, dtype=np.intp)
        ext_idx = start + np.asarray(pc_, dtype=np.int64)

        t_obs = np.fromiter(
            (e.timestamp for e in history), dtype=np.float64, count=history_length
        )
        t_in = t_obs[po]
        t_sc = np.asarray(self.score.time_for_index(ext_idx), dtype=np.float64)
        speed, rhythm = self._rhythm(t_in, t_sc)

        position = int(ext_idx[-1] % score_length)
        matched = len(po)
        combined = best_cost + RHYTHM_WEIGHT * (1.0 - rhythm)
        confidence = math.exp(-2.0 * combined) * (matched / history_length)

        # ---- ambiguity: best rival alignment at a different place
        dd = np.abs(s_idx - int(s_idx[c_best]))
        dd = np.minimum(dd, score_length - dd)
        rival = dd > SECOND_BEST_GUARD
        if rival.any():
            second = float(raw[rival].min())
            margin = (second - best_cost) / max(second, 1e-9)
            confidence *= 0.80 + 0.20 * min(1.0, max(0.0, margin))

        return MatchResult(
            position=position,
            confidence=confidence,
            cost=combined,
            matched_events=matched,
            tempo_ratio=speed,
            rhythm_score=rhythm,
            timestamp=float(t_in[-1]),
            n_observed=history_length,
        )


# ============================================================
# TEMPO ESTIMATOR
# ============================================================


class TempoEstimator:

    def __init__(self):
        self.history = deque(maxlen=TEMPO_HISTORY_SIZE)
        self.speed = 1.0
        self.locked = False

    def reset(self):
        self.history.clear()
        self.speed = 1.0
        self.locked = False

    def update(self, result):
        if (
            result is None
            or result.tempo_ratio is None
            or result.matched_events < 4
            or result.rhythm_score < 0.45
        ):
            return self.speed
        self.history.append(result.tempo_ratio)
        stable = float(np.median(self.history))
        if not self.locked:
            self.speed = stable  # first reliable estimate: adopt it directly
            self.locked = True
        else:
            self.speed += TEMPO_SMOOTHING * (stable - self.speed)
        self.speed = float(np.clip(self.speed, MIN_PLAYBACK_SPEED, MAX_PLAYBACK_SPEED))
        return self.speed


# ============================================================
# METRICAL TRACKER (acquisition evidence)
# ============================================================


class MetricalTracker:
    """Collects confident results that form a coherent, advancing trajectory."""

    def __init__(self, score):
        self.score = score
        self.evidence = deque()

    def reset(self):
        self.evidence.clear()

    def add(self, result, new_events):
        score = self.score
        beat = 0.0
        if self.evidence:
            prev = self.evidence[-1]
            d = score.event_delta(prev.position, result.position)
            if (
                -CONSIST_BACK
                <= d
                <= CONSIST_FWD_PER_EVENT * max(new_events, 1) + CONSIST_SLACK
            ):
                beat = prev.beat + score.beat_delta(prev.position, result.position)
            else:
                self.evidence.clear()  # trajectory broke: start over from this result
        self.evidence.append(
            Evidence(result.timestamp, beat, result.confidence, result.position)
        )
        while len(self.evidence) > 1 and (
            self.evidence[0].beat < beat - EVIDENCE_WINDOW_BEATS
            or result.timestamp - self.evidence[0].timestamp > EVIDENCE_MAX_AGE
        ):
            self.evidence.popleft()

    def summary(self):
        if not self.evidence:
            return 0.0, 0, 0.0
        conf = float(np.mean([e.confidence for e in self.evidence]))
        span = self.evidence[-1].beat - self.evidence[0].beat
        return conf, len(self.evidence), span

    def is_reliable(self, needed, threshold):
        conf, count, span = self.summary()
        return (
            count >= max(needed, MIN_EVIDENCE_MATCHES)
            and span >= MIN_EVIDENCE_SPAN_BEATS
            and conf >= threshold
        )


# ============================================================
# MIDI PLAYBACK
# ============================================================


class MIDIPlayback:
    """One persistent thread. The musical clock is an immutable tuple
    (anchor_wall, anchor_score, speed) that is replaced atomically, so the
    main thread can read it lock-free and the player never sees a torn state.
    """

    def __init__(self, score, port_name, loop=True):
        self.score = score
        self.port_name = port_name
        self.loop = loop
        self.port = None
        self.thread = None

        self.cv = threading.Condition()
        self._clock = None
        self._version = 0
        self._epoch = 0
        self._next = 0
        self._shutdown = False
        self._idle = threading.Event()
        self._idle.set()

        self._on = [
            mido.Message("note_on", note=p, velocity=MIDI_VELOCITY) for p in range(128)
        ]
        self._off = [mido.Message("note_off", note=p, velocity=0) for p in range(128)]
        self._panic = [
            mido.Message("control_change", control=64, value=0),
            mido.Message("control_change", control=123, value=0),
        ]
        self._et = score.event_times.tolist()

    # ---------------------------------------------------- lifecycle

    def open(self):
        print("Opening MIDI output:", self.port_name)
        self.port = mido.open_output(self.port_name)
        self.thread = threading.Thread(target=self._run, name="playback", daemon=True)
        self.thread.start()

    def stop(self):
        """Silence and go idle (blocks briefly until every note is released)."""
        with self.cv:
            self._clock = None
            self._version += 1
            self._idle.clear()
            self.cv.notify_all()
        self._idle.wait(1.0)

    def shutdown(self):
        with self.cv:
            self._shutdown = True
            self._clock = None
            self._version += 1
            self.cv.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        if self.port is not None and not (self.thread and self.thread.is_alive()):
            try:
                for msg in self._panic:
                    self.port.send(msg)
                self.port.close()
            except Exception:
                pass

    # ---------------------------------------------------- control (any thread)

    def seek(self, index, wall_time, speed):
        """The performer was at event `index` at `wall_time`: play on from index+1."""
        speed = float(np.clip(speed, MIN_PLAYBACK_SPEED, MAX_PLAYBACK_SPEED))
        with self.cv:
            self._clock = (float(wall_time), float(self._et[index]), speed)
            self._next = index + 1
            self._epoch += 1
            self._version += 1
            self._idle.clear()
            self.cv.notify_all()

    def nudge(self, delta):
        """Shift the musical clock by `delta` score-seconds (phase correction)."""
        with self.cv:
            c = self._clock
            if c is None:
                return
            self._clock = (c[0], c[1] + delta, c[2])
            self._version += 1
            self.cv.notify_all()

    def set_speed(self, speed):
        speed = float(np.clip(speed, MIN_PLAYBACK_SPEED, MAX_PLAYBACK_SPEED))
        with self.cv:
            c = self._clock
            if c is None:
                return
            now = time.perf_counter()
            self._clock = (now, c[1] + (now - c[0]) * c[2], speed)
            self._version += 1
            self.cv.notify_all()

    # ---------------------------------------------------- queries (lock-free)

    def clock(self):
        return self._clock

    def is_playing(self):
        return self._clock is not None

    def index_at(self, timestamp):
        c = self._clock
        if c is None:
            return None
        t = c[1] + (timestamp - c[0]) * c[2]
        if self.loop:
            t %= self.score.loop_duration
        else:
            t = min(max(t, 0.0), self._et[-1])
        i = int(np.searchsorted(self.score.event_times, t, side="right")) - 1
        return max(0, min(i, self.score.n - 1))

    # ---------------------------------------------------- player thread

    def _release_all(self, active, note_offs, panic=False):
        send = self.port.send
        for pitch in tuple(active):
            send(self._off[pitch])
        active.clear()
        note_offs.clear()
        if panic:
            for msg in self._panic:
                send(msg)

    def _run(self):
        score = self.score
        n = score.n
        L = score.loop_duration
        et = self._et
        notes = score.event_notes
        loop = self.loop
        pc = time.perf_counter
        send = self.port.send
        on, off = self._on, self._off

        note_offs = []  # heap of (score_time, seq, pitch)
        active = {}  # pitch -> seq of the note currently sounding
        seq = 0
        my_epoch = -1
        g = 0

        while True:
            try:
                with self.cv:
                    while True:
                        if self._shutdown:
                            self._release_all(active, note_offs, panic=True)
                            self._idle.set()
                            return
                        if self._clock is not None:
                            break
                        self._release_all(active, note_offs, panic=True)
                        self._idle.set()
                        self.cv.wait()
                    clock = self._clock
                    version = self._version
                    if self._epoch != my_epoch:
                        my_epoch = self._epoch
                        self._release_all(active, note_offs)
                        g = self._next

                aw, as_, sp = clock
                now = pc()
                musical = as_ + (now - aw) * sp

                while note_offs and note_offs[0][0] <= musical:
                    _, s, pitch = heapq.heappop(note_offs)
                    if active.get(pitch) == s:
                        send(off[pitch])
                        del active[pitch]

                if g >= n and not loop:
                    if not note_offs:  # piece finished
                        with self.cv:
                            if self._version == version:
                                self._clock = None
                                self._version += 1
                        continue
                    wake = aw + (note_offs[0][0] - as_) / sp
                else:
                    cyc, idx = divmod(g, n)
                    t_ev = cyc * L + et[idx]
                    due = aw + (t_ev - as_) / sp
                    if due <= now:
                        if now - due <= MAX_LATE_SECONDS:
                            for pitch, dur in notes[idx]:
                                if pitch in active:
                                    send(off[pitch])
                                send(on[pitch])
                                seq += 1
                                active[pitch] = seq
                                heapq.heappush(note_offs, (t_ev + dur, seq, pitch))
                        g += 1
                        continue
                    wake = due
                    if note_offs:
                        wake = min(wake, aw + (note_offs[0][0] - as_) / sp)

                delay = wake - now
                if delay > SPIN_SECONDS + 0.0005:
                    with self.cv:
                        if self._version == version and not self._shutdown:
                            self.cv.wait(delay - SPIN_SECONDS)
                else:
                    while pc() < wake:
                        time.sleep(0)
            except Exception as exc:  # never let the player thread die silently
                print("PLAYBACK ERROR:", repr(exc))
                try:
                    with self.cv:
                        self._clock = None
                        self._version += 1
                    active.clear()
                    note_offs.clear()
                except Exception:
                    pass
                time.sleep(0.05)


# ============================================================
# APPLICATION
# ============================================================


class Application:

    def __init__(
        self,
        filename,
        input_port,
        output_port,
        threshold=CONFIDENCE_THRESHOLD,
        mismatch_confirmations=7,
        mismatch_distance=12.0,
        reacquire_confirmations=3,
        collection_time=STARTUP_COLLECTION_SECONDS,
        loop=True,
    ):
        self.score = Score(filename)
        self.loop = loop
        self.midi_input = MIDIInput(input_port)
        self.playback = MIDIPlayback(self.score, output_port, loop=loop)
        self.follower = ScoreFollower(self.score)
        self.tempo = TempoEstimator()
        self.tracker = MetricalTracker(self.score)
        self.grouper = NoteGrouper(GROUPING_WINDOW)

        self.threshold = threshold
        self.mismatch_confirmations = max(1, mismatch_confirmations)
        self.mismatch_distance = mismatch_distance
        self.reacquire_confirmations = max(1, reacquire_confirmations)
        self.collection_time = collection_time

        self.mode = "SEARCHING"
        self.first_input_timestamp = None
        self.alt = None  # [last_position, count] of a disagreeing trajectory
        self.last_speed_update = 0.0
        self.since_global = 0
        self.stats = {"batches": 0, "total": 0.0, "max": 0.0}
        self.first_play_time = None

        # Free the (large) music21 object graph and exempt the rest from GC scans.
        gc.collect()
        gc.freeze()

    # ---------------------------------------------------- state changes

    def enter_searching(self, reason):
        print("\n--- %s: searching for position ---" % reason)
        self.playback.stop()
        self.mode = "SEARCHING"
        self.follower.reset()
        self.tempo.reset()
        self.tracker.reset()
        self.alt = None

    def start_playback(self, result):
        speed = self.tempo.speed
        print("\n================================")
        print("SCORE POSITION CONFIRMED")
        print("Position:", result.position, "of", self.score.n)
        print("Confidence:", round(result.confidence, 3))
        print("Tempo ratio:", round(speed, 3))
        print("================================")
        self.playback.seek(result.position, result.timestamp, speed)
        self.mode = "PLAYING"
        self.alt = None
        self.tracker.reset()
        self.last_speed_update = time.perf_counter()
        self.since_global = 0
        if self.first_play_time is None:
            self.first_play_time = time.perf_counter()

    def relock(self, result):
        print("\n================================")
        print("NEW SCORE POSITION CONFIRMED:", result.position)
        print("================================")
        self.playback.seek(result.position, result.timestamp, self.tempo.speed)
        self.alt = None
        self.tracker.reset()
        self.since_global = 0

    # ---------------------------------------------------- per-result logic

    def acquire(self, result, new_events):
        if result.confidence < self.threshold:
            return
        self.tempo.update(result)
        self.tracker.add(result, new_events)
        if not self.tracker.is_reliable(self.reacquire_confirmations, self.threshold):
            return
        if (
            self.first_input_timestamp is None
            or result.timestamp - self.first_input_timestamp < self.collection_time
        ):
            return
        conf, count, span = self.tracker.summary()
        print(
            "ACQUISITION: confidence %.3f, matches %d, metrical span %.2f beats"
            % (conf, count, span)
        )
        self.start_playback(result)

    def track(self, result, new_events):
        clock = self.playback.clock()
        if clock is None:
            self.enter_searching("Playback ended")
            return
        if result.confidence < self.threshold:
            return

        t = result.timestamp
        current = clock[1] + (t - clock[0]) * clock[2]
        target = float(self.score.event_times[result.position])
        err = self.score.wrap_time(target - current) if self.loop else target - current
        if VERBOSE:
            print(
                "   TRACK: err %+.3f s | playback speed %.3f | est speed %.3f"
                % (err, clock[2], self.tempo.speed)
            )

        if abs(err) <= RESYNC_SECONDS:
            # Agreement: follow tempo and correct phase smoothly.
            self.alt = None
            speed = self.tempo.update(result)
            self.follower.speed_hint = speed
            now = time.perf_counter()
            if (
                now - self.last_speed_update > SPEED_UPDATE_INTERVAL
                and abs(speed - clock[2]) > 0.005 * clock[2]
            ):
                self.playback.set_speed(speed)
                self.last_speed_update = now
            if abs(err) > SYNC_DEADBAND:
                self.playback.nudge(SYNC_GAIN * err)
            return

        # Disagreement: the performer is somewhere else than we are playing.
        expected = self.playback.index_at(t)
        dist_beats = (
            self.score.beat_distance(result.position, expected)
            if expected is not None
            else 0.0
        )
        if self.alt is not None and (
            -CONSIST_BACK
            <= self.score.event_delta(self.alt[0], result.position)
            <= CONSIST_FWD_PER_EVENT * max(new_events, 1) + CONSIST_SLACK
        ):
            self.alt[0] = result.position
            self.alt[1] += 1
        else:
            self.alt = [result.position, 1]
        needed = (
            2 if dist_beats <= self.mismatch_distance else self.mismatch_confirmations
        )
        if self.alt[1] >= needed:
            self.relock(result)

    # ---------------------------------------------------- event processing

    def process(self, events):
        t_start = time.perf_counter()
        for ev in events:
            if self.first_input_timestamp is None:
                self.first_input_timestamp = ev.timestamp
                print("\nCollecting initial MIDI data...")
            self.follower.add(ev)

        if self.follower.ready():
            last = events[-1]
            playing = self.mode == "PLAYING"
            expected = self.playback.index_at(last.timestamp) if playing else None
            if playing and expected is None:
                self.enter_searching("Playback ended")
                playing = False
            windowed = False
            if playing and self.score.n > WINDOWED_SCORE_EVENTS:
                self.since_global += 1
                if self.since_global < GLOBAL_CHECK_EVERY:
                    windowed = True
                else:
                    self.since_global = 0
            result = self.follower.align(expected, windowed)
            if result is not None:
                if VERBOSE:
                    print(
                        "MATCH: pos %d | conf %.3f | rhythm %.3f | speed %s | matched %d/%d"
                        % (
                            result.position,
                            result.confidence,
                            result.rhythm_score,
                            (
                                "-"
                                if result.tempo_ratio is None
                                else "%.2f" % result.tempo_ratio
                            ),
                            result.matched_events,
                            result.n_observed,
                        )
                    )
                if self.mode == "PLAYING":
                    self.track(result, len(events))
                else:
                    self.acquire(result, len(events))

        dt = time.perf_counter() - t_start
        s = self.stats
        s["batches"] += 1
        s["total"] += dt
        s["max"] = max(s["max"], dt)

    def housekeeping(self):
        if self.mode == "PLAYING" and not self.playback.is_playing():
            self.enter_searching("Playback ended")

    # ---------------------------------------------------- main loop

    def run(self, stop_event=None):
        print("\n================================")
        print("REAL-TIME SCORE FOLLOWER")
        print("================================")
        print("Score events:", self.score.n)
        print("Confidence threshold:", self.threshold)
        print("Initial collection:", self.collection_time, "seconds")
        print("Looping:", "yes" if self.loop else "no")

        self.playback.open()
        try:
            self.midi_input.start()
        except Exception:
            self.playback.shutdown()
            raise
        print("\nWaiting for MIDI input...")

        q = self.midi_input.queue
        grouper = self.grouper
        pc = time.perf_counter
        try:
            while stop_event is None or not stop_event.is_set():
                deadline = grouper.deadline()
                timeout = (
                    IDLE_TICK
                    if deadline is None
                    else min(IDLE_TICK, max(0.0, deadline - pc()))
                )
                items = []
                try:
                    items.append(q.get(timeout=timeout))
                    while True:
                        items.append(q.get_nowait())
                except queue.Empty:
                    pass

                input_sequence = []
                for t, pitch in items:
                    ev = grouper.feed(t, pitch)
                    if ev is not None:
                        input_sequence.append(ev)

                ev = grouper.poll(pc())
                if ev is not None:
                    input_sequence.append(ev)

                if input_sequence:
                    self.process(input_sequence)
                else:
                    self.housekeeping()
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            self.midi_input.stop()
            self.playback.shutdown()
            print("Application stopped.")


# ============================================================
# MIDI PORT DISCOVERY
# ============================================================


def list_ports():
    print("\nMIDI INPUT PORTS:")
    for name in mido.get_input_names():
        print(" ", name)
    print("\nMIDI OUTPUT PORTS:")
    for name in mido.get_output_names():
        print(" ", name)


def resolve_port(wanted, names, kind):
    if wanted in names:
        return wanted
    matches = [n for n in names if wanted.lower() in n.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        sys.exit(
            "No MIDI %s port matches %r. Available: %s"
            % (kind, wanted, names or "none")
        )
    sys.exit("MIDI %s port %r is ambiguous: %s" % (kind, wanted, matches))


# ============================================================
# SELF-TEST (simulated performer + mock MIDI ports)
# ============================================================


class _FakeInput:
    def __init__(self, callback):
        self.callback = callback

    def close(self):
        pass


class _FakeOutput:
    def __init__(self):
        self.log = []

    def send(self, msg):
        self.log.append(
            (
                time.perf_counter(),
                msg.type,
                getattr(msg, "note", None),
                getattr(msg, "control", None),
            )
        )

    def close(self):
        pass


def run_selftest(args):
    rng = np.random.default_rng(7)
    path = args.score
    if not path:
        from music21 import corpus

        path = str(corpus.getWork("bach/bwv66.6"))

    fake_out = _FakeOutput()
    holder = {}

    def fake_open_input(name, callback=None, **kw):
        holder["in"] = _FakeInput(callback)
        return holder["in"]

    mido.open_input = fake_open_input
    mido.open_output = lambda name, **kw: fake_out

    app = Application(
        path, "SELFTEST-IN", "SELFTEST-OUT", collection_time=args.collection_time
    )
    score = app.score
    et = score.event_times
    n = score.n
    stop = threading.Event()
    perf_log = []  # (time, intended pitches, segment, seconds since segment start)

    def performer():
        while "in" not in holder:
            time.sleep(0.01)
        cb = holder["in"].callback
        speed0 = args.selftest_speed
        total = args.selftest_seconds
        seg_len = [0.55 * total, 0.45 * total]
        starts = [int(n * 0.15), int((n * 0.15 + n * 0.5)) % n]
        t_begin = time.perf_counter() + 0.3
        for seg in range(2):
            idx = starts[seg]
            t_seg0 = time.perf_counter() if seg else t_begin
            wall = 0.0
            while wall < seg_len[seg]:
                nxt = (idx + 1) % n
                dscore = et[nxt] - et[idx] if nxt else score.loop_duration - et[idx]
                drift = 1.0 + 0.08 * math.sin(
                    2 * math.pi * (time.perf_counter() - t_begin) / 17.0
                )
                wall += max(dscore, 0.02) / (speed0 * drift)
                idx = nxt
                target = t_seg0 + wall + rng.normal(0, 0.012)
                delay = target - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
                pitches = [p for p in score.events[idx].pitches if rng.random() > 0.08]
                if not pitches:
                    continue
                pitches = [
                    (
                        min(127, max(0, p + int(rng.choice([-2, -1, 1, 2]))))
                        if rng.random() < 0.04
                        else p
                    )
                    for p in pitches
                ]
                perf_log.append(
                    (
                        time.perf_counter(),
                        score.events[idx].pitches,
                        seg,
                        time.perf_counter() - t_seg0,
                    )
                )
                for p in pitches:
                    cb(mido.Message("note_on", note=int(p), velocity=70))
                    time.sleep(float(rng.uniform(0, 0.012)))
        time.sleep(1.5)
        stop.set()

    threading.Thread(target=performer, daemon=True).start()
    app.run(stop)

    # ---------------- evaluation
    ons, sounding = {}, set()
    for t, typ, nt, ctrl in fake_out.log:
        if typ == "note_on":
            ons.setdefault(nt, []).append(t)
            sounding.add(nt)
        elif typ == "note_off":
            sounding.discard(nt)
        elif typ == "control_change" and ctrl == 123:
            sounding.clear()
    ons = {k: np.asarray(v) for k, v in ons.items()}

    steady_after = [
        0.55 * args.selftest_seconds * 0.45,
        0.45 * args.selftest_seconds * 0.5,
    ]
    lags = {0: [], 1: []}
    missing = {0: 0, 1: 0}
    for t, pitches, seg, since in perf_log:
        if since < steady_after[seg]:
            continue
        times = ons.get(max(pitches))
        lag = None
        if times is not None and len(times):
            j = int(np.argmin(np.abs(times - t)))
            if abs(times[j] - t) < 0.35:
                lag = float(times[j] - t)
        if lag is None:
            missing[seg] += 1
        else:
            lags[seg].append(lag)

    print("\n================ SELFTEST RESULT ================")
    ok = True
    for seg, label in ((0, "initial lock"), (1, "after jump")):
        L = np.abs(np.asarray(lags[seg]))
        total = len(lags[seg]) + missing[seg]
        if total == 0 or len(L) == 0:
            print("%-13s: no steady-state events" % label)
            ok = False
            continue
        within = float(np.mean(L < 0.10))
        print(
            "%-13s: events %3d | played by follower %3d | median |lag| %5.1f ms | p90 %5.1f ms | within 100ms %3.0f%%"
            % (
                label,
                total,
                len(L),
                1000 * np.median(L),
                1000 * np.percentile(L, 90),
                100 * within,
            )
        )
        if len(L) / total < 0.8 or within < 0.7:
            ok = False
    s = app.stats
    print(
        "processing    : %d batches | mean %.2f ms | max %.2f ms"
        % (s["batches"], 1000 * s["total"] / max(s["batches"], 1), 1000 * s["max"])
    )
    print("stuck notes   :", sorted(sounding) if sounding else "none")
    ok = ok and not sounding
    print("RESULT        :", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# ============================================================
# MAIN
# ============================================================


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(description="Real-time MIDI score follower")
    parser.add_argument("score", nargs="?")
    parser.add_argument("--input", help="MIDI input port (substring is enough)")
    parser.add_argument("--output", help="MIDI output port (substring is enough)")
    parser.add_argument("--threshold", type=float, default=CONFIDENCE_THRESHOLD)
    parser.add_argument(
        "--mismatch-confirmations",
        type=int,
        default=7,
        help="Consistent contradicting results needed to follow a far jump.",
    )
    parser.add_argument(
        "--mismatch-distance",
        type=float,
        default=12.0,
        help="Distance in beats above which a disagreement counts as a jump.",
    )
    parser.add_argument(
        "--reacquire-confirmations",
        type=int,
        default=3,
        help="Consistent confident results needed to lock on.",
    )
    parser.add_argument(
        "--collection-time",
        type=float,
        default=STARTUP_COLLECTION_SECONDS,
        help="Initial MIDI data collection period in seconds.",
    )
    parser.add_argument(
        "--no-loop",
        action="store_true",
        help="Stop at the end of the score instead of looping.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print every alignment result."
    )
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Simulate a performer against mock MIDI ports (no hardware).",
    )
    parser.add_argument("--selftest-seconds", type=float, default=32.0)
    parser.add_argument("--selftest-speed", type=float, default=1.25)
    args = parser.parse_args()

    VERBOSE = args.verbose
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    try:
        sys.setswitchinterval(0.0005)  # let the MIDI/player threads preempt quickly
    except Exception:
        pass

    if args.list_ports:
        list_ports()
        return 0

    if args.selftest:
        return run_selftest(args)

    if not args.score:
        parser.error("Score file required.")
    if not args.input:
        parser.error("--input required.")
    if not args.output:
        parser.error("--output required.")
    if not 0 <= args.threshold <= 1:
        parser.error("Threshold must be between 0 and 1.")
    if args.collection_time < 0:
        parser.error("Collection time cannot be negative.")

    in_name = resolve_port(args.input, mido.get_input_names(), "input")
    out_name = resolve_port(args.output, mido.get_output_names(), "output")
    if in_name == out_name:
        print(
            "WARNING: input and output are the same port; this can create a feedback loop."
        )

    app = Application(
        filename=args.score,
        input_port=in_name,
        output_port=out_name,
        threshold=args.threshold,
        mismatch_confirmations=args.mismatch_confirmations,
        mismatch_distance=args.mismatch_distance,
        reacquire_confirmations=args.reacquire_confirmations,
        collection_time=args.collection_time,
        loop=not args.no_loop,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
