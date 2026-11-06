#!/usr/bin/env python3

import argparse
import heapq
import math
import queue
import statistics
import threading
import time

from collections import deque
from dataclasses import dataclass

import numpy as np
import mido

from music21 import converter, note, chord, tempo, stream

# ============================================================
# OPTIONAL NUMBA
# ============================================================

try:
    from numba import njit

    NUMBA_AVAILABLE = True

except ImportError:
    NUMBA_AVAILABLE = False

    def njit(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]

        def decorator(func):
            return func

        return decorator


# ============================================================
# CONFIGURATION
# ============================================================


@dataclass
class Config:

    # MIDI input
    grouping_window: float = 0.060
    input_poll_sleep: float = 0.001
    input_queue_timeout: float = 0.1
    main_loop_sleep: float = 0.005

    # History
    history_bars: int = 4
    min_history: int = 6

    # Confidence
    confidence_threshold: float = 0.68

    # Alignment
    insertion_cost: float = 0.20
    deletion_cost: float = 0.45
    max_alignment_multiplier: int = 2
    max_alignment_extra: int = 4
    candidate_limit: int = 12

    # Duplicate-section handling
    ambiguity_cost_margin: float = 0.05
    continuity_weight: float = 1.0

    # Pitch matching
    pitch_distance_sigma: float = 2.5

    # Rhythm
    rhythm_weight: float = 0.20
    rhythm_sigma: float = 0.35
    min_input_interval: float = 0.025

    # Metrical tracking
    evidence_window_beats: float = 2.0
    min_evidence_matches: int = 3
    min_evidence_span: float = 0.75

    # Mismatch tracking
    mismatch_duration_beats: float = 1.5
    mismatch_distance: float = 12.0
    position_change_margin: float = 0.20
    mismatch_confirmations: int = 7
    reacquire_confirmations: int = 3

    # Tempo
    tempo_history_size: int = 20
    tempo_smoothing: float = 0.20
    min_playback_speed: float = 0.5
    max_playback_speed: float = 2.5
    min_tempo_matches: int = 4
    min_tempo_rhythm_score: float = 0.45
    initial_seconds_per_beat: float = 0.5
    metrical_tempo_smoothing: float = 0.15

    # Playback
    midi_velocity: int = 85
    scheduler_sleep: float = 0.002
    thread_join_timeout: float = 5.0
    minimum_note_duration: float = 0.01
    playback_speed_update_interval: float = 0.10

    # Acquisition
    acquisition_confidence_threshold: float = 0.68

    # Diagnostics
    verbose: bool = True


# ============================================================
# NUMBA ALIGNMENT ENGINE
# ============================================================


@njit(cache=True, fastmath=True)
def pitch_similarity(mask_a, mask_b, sigma):

    if mask_a == 0 or mask_b == 0:
        return 0.0

    best = 0.0

    for a in range(12):

        if not (mask_a & (1 << a)):
            continue

        for b in range(12):

            if not (mask_b & (1 << b)):
                continue

            distance = abs(a - b)

            if distance > 6:
                distance = 12 - distance

            value = math.exp(-0.5 * (distance / sigma) ** 2)

            if value > best:
                best = value

    return best


@njit(cache=True, fastmath=True)
def evaluate_candidates(
    observed, score, starts, length, insertion_cost, deletion_cost, sigma
):

    n = len(observed)
    candidate_count = len(starts)
    score_length = len(score)

    costs = np.full(candidate_count, np.inf, dtype=np.float64)

    endpoints = np.zeros(candidate_count, dtype=np.int32)

    previous = np.empty(length + 1, dtype=np.float64)

    current = np.empty(length + 1, dtype=np.float64)

    for candidate in range(candidate_count):

        start = starts[candidate]

        previous[:] = np.inf
        previous[0] = 0.0

        for j in range(1, length + 1):
            previous[j] = previous[j - 1] + deletion_cost

        for i in range(1, n + 1):

            current[0] = i * insertion_cost

            observed_mask = observed[i - 1]

            for j in range(1, length + 1):

                score_index = (start + j - 1) % score_length

                similarity = pitch_similarity(observed_mask, score[score_index], sigma)

                match = previous[j - 1] + 1.0 - similarity

                insertion = previous[j] + insertion_cost

                deletion = current[j - 1] + deletion_cost

                if match <= insertion and match <= deletion:

                    current[j] = match

                elif insertion <= deletion:

                    current[j] = insertion

                else:

                    current[j] = deletion

            previous, current = current, previous

        best_cost = np.inf
        best_end = 1

        for j in range(1, length + 1):

            if previous[j] < best_cost:

                best_cost = previous[j]
                best_end = j

        costs[candidate] = best_cost / n
        endpoints[candidate] = best_end

    return costs, endpoints


@njit(cache=True, fastmath=True)
def build_traceback(
    observed, score, start, length, insertion_cost, deletion_cost, sigma
):

    n = len(observed)
    score_length = len(score)

    dp = np.full((n + 1, length + 1), np.inf, dtype=np.float64)

    trace = np.zeros((n + 1, length + 1), dtype=np.uint8)

    dp[0, 0] = 0.0

    for i in range(1, n + 1):

        dp[i, 0] = dp[i - 1, 0] + insertion_cost

        trace[i, 0] = 1

    for j in range(1, length + 1):

        dp[0, j] = dp[0, j - 1] + deletion_cost

        trace[0, j] = 2

    for i in range(1, n + 1):

        observed_mask = observed[i - 1]

        for j in range(1, length + 1):

            score_index = (start + j - 1) % score_length

            similarity = pitch_similarity(observed_mask, score[score_index], sigma)

            match = dp[i - 1, j - 1] + 1.0 - similarity

            insertion = dp[i - 1, j] + insertion_cost

            deletion = dp[i, j - 1] + deletion_cost

            if match <= insertion and match <= deletion:

                dp[i, j] = match
                trace[i, j] = 0

            elif insertion <= deletion:

                dp[i, j] = insertion
                trace[i, j] = 1

            else:

                dp[i, j] = deletion
                trace[i, j] = 2

    return trace


# ============================================================
# DATA STRUCTURES
# ============================================================


@dataclass
class ScoreEvent:
    position: float
    duration: float
    pitches: frozenset


@dataclass
class InputEvent:
    timestamp: float
    pitches: frozenset


@dataclass
class MatchResult:
    position: int
    confidence: float
    cost: float
    matched_events: int
    matched_pairs: list
    tempo_ratio: float
    rhythm_score: float


@dataclass
class Evidence:
    timestamp: float
    beat: float
    confidence: float
    position: int
    matched: bool


# ============================================================
# PITCH CONVERSION
# ============================================================


def pitches_to_mask(pitches):

    mask = 0

    for pitch in pitches:
        mask |= 1 << (int(pitch) % 12)

    return mask


# ============================================================
# SCORE LOADING
# ============================================================


class Score:

    def __init__(self, filename):

        self.events = []
        self.tempos = [(0.0, 120.0)]

        self.loop_start = 0.0
        self.loop_end = 0.0
        self.loop_duration = 0.0

        self.bar_positions = []
        self.bar_duration = 4.0

        self.event_times = None
        self.event_beats = None
        self.event_durations_seconds = None

        self.load(filename)

    @staticmethod
    def expand_repeats(parsed):

        if parsed.parts:

            result = stream.Score()

            for part in parsed.parts:

                measured = part

                if not list(measured.getElementsByClass(stream.Measure)):

                    measured = measured.makeMeasures()

                try:
                    expanded = measured.expandRepeats()

                except Exception as exc:

                    print("Repeat expansion warning:", exc)

                    expanded = measured

                result.insert(0, expanded)

            return result

        measured = parsed

        if not list(measured.getElementsByClass(stream.Measure)):

            measured = measured.makeMeasures()

        try:
            return measured.expandRepeats()

        except Exception as exc:

            print("Repeat expansion warning:", exc)

            return measured

    def load(self, filename):

        print("Loading:", filename)

        parsed = converter.parse(filename)
        expanded = self.expand_repeats(parsed)

        flat = expanded.flatten()

        marks = []

        for mark in flat.getElementsByClass(tempo.MetronomeMark):

            if mark.number and mark.number > 0:

                marks.append((float(mark.offset), float(mark.number)))

        if marks:

            self.tempos = sorted(marks)

            if self.tempos[0][0] > 0:

                self.tempos.insert(0, (0.0, 120.0))

        self.tempo_positions = np.array([x[0] for x in self.tempos], dtype=np.float64)

        self.tempo_values = np.array([x[1] for x in self.tempos], dtype=np.float64)

        measures = list(flat.getElementsByClass(stream.Measure))

        if measures:

            self.bar_positions = sorted(
                set(round(float(m.offset), 6) for m in measures)
            )

            differences = [
                self.bar_positions[i + 1] - self.bar_positions[i]
                for i in range(len(self.bar_positions) - 1)
                if (self.bar_positions[i + 1] > self.bar_positions[i])
            ]

            if differences:

                self.bar_duration = statistics.median(differences)

        grouped = {}

        for element in flat.notes:

            position = round(float(element.offset), 6)

            if isinstance(element, note.Note):

                pitches = [element.pitch.midi]

            elif isinstance(element, chord.Chord):

                pitches = [p.midi for p in element.pitches]

            else:
                continue

            event = grouped.setdefault(position, {"pitches": set(), "duration": 0.0})

            event["pitches"].update(pitches)

            event["duration"] = max(
                event["duration"], float(element.duration.quarterLength)
            )

        self.events = [
            ScoreEvent(
                position=position,
                duration=data["duration"],
                pitches=frozenset(data["pitches"]),
            )
            for position, data in sorted(grouped.items())
        ]

        if not self.events:
            raise ValueError("No playable notes found.")

        self.loop_start = self.events[0].position

        self.loop_end = max(event.position + event.duration for event in self.events)

        self.precompute_timing()

        self.loop_duration = self.position_to_seconds(
            self.loop_end
        ) - self.position_to_seconds(self.loop_start)

        if self.loop_duration <= 0:
            raise ValueError("Invalid score duration.")

        print("Score events:", len(self.events))
        print("Score bars:", len(self.bar_positions))
        print("Average bar duration:", self.bar_duration)
        print("Loop duration:", round(self.loop_duration, 2))

    def position_to_seconds(self, position):

        index = np.searchsorted(self.tempo_positions, position, side="left")

        seconds = 0.0
        current_position = 0.0
        current_bpm = 120.0

        for i in range(index):

            change_position = self.tempo_positions[i]
            change_bpm = self.tempo_values[i]

            if change_position <= current_position:

                current_bpm = change_bpm
                continue

            seconds += (change_position - current_position) * 60.0 / current_bpm

            current_position = change_position
            current_bpm = change_bpm

        if index < len(self.tempo_positions):

            change_position = self.tempo_positions[index]

            if change_position > current_position:

                seconds += (change_position - current_position) * 60.0 / current_bpm

                current_position = change_position

            current_bpm = self.tempo_values[index]

        if position > current_position:

            seconds += (position - current_position) * 60.0 / current_bpm

        return seconds

    def precompute_timing(self):

        n = len(self.events)

        self.event_times = np.empty(n, dtype=np.float64)

        self.event_beats = np.empty(n, dtype=np.float64)

        self.event_durations_seconds = np.empty(n, dtype=np.float64)

        loop_start_seconds = self.position_to_seconds(self.loop_start)

        for i, event in enumerate(self.events):

            self.event_times[i] = (
                self.position_to_seconds(event.position) - loop_start_seconds
            )

            self.event_beats[i] = event.position - self.loop_start

            self.event_durations_seconds[i] = self.position_to_seconds(
                event.position + event.duration
            ) - self.position_to_seconds(event.position)

        self.event_times = np.ascontiguousarray(self.event_times)

        self.event_beats = np.ascontiguousarray(self.event_beats)

        self.event_durations_seconds = np.ascontiguousarray(
            self.event_durations_seconds
        )

    def event_time(self, index):
        return self.event_times[index]

    def event_beat(self, index):
        return self.event_beats[index]

    def score_time_for_index(self, index):

        cycle, event_index = divmod(index, len(self.events))

        return cycle * self.loop_duration + self.event_times[event_index]

    def circular_distance(self, a, b):

        n = len(self.events)

        return min((a - b) % n, (b - a) % n)

    def beat_distance(self, a, b):

        total_beats = self.loop_end - self.loop_start

        if total_beats <= 0:
            return 0.0

        difference = abs(self.event_beats[a] - self.event_beats[b])

        return min(difference, total_beats - difference)

    def history_window_seconds(self, cfg):

        if len(self.bar_positions) > 1:

            start = self.bar_positions[0]

            target_index = min(cfg.history_bars, len(self.bar_positions) - 1)

            end = self.bar_positions[target_index]

            return max(
                1.0, self.position_to_seconds(end) - self.position_to_seconds(start)
            )

        return max(1.0, cfg.history_bars * self.bar_duration * 0.5)


# ============================================================
# MIDI INPUT
# ============================================================


class MIDIInput:

    def __init__(self, port_name, cfg):

        self.port_name = port_name
        self.cfg = cfg

        self.raw_queue = queue.Queue()
        self.event_queue = queue.Queue()

        self.running = False

        self.listener_thread = None
        self.aggregator_thread = None

    def start(self):

        self.running = True

        self.listener_thread = threading.Thread(target=self.listen, daemon=True)

        self.aggregator_thread = threading.Thread(target=self.aggregate, daemon=True)

        self.listener_thread.start()
        self.aggregator_thread.start()

    def listen(self):

        print("Opening MIDI input:", self.port_name)

        try:

            with mido.open_input(self.port_name) as port:

                while self.running:

                    message = port.poll()

                    if message is None:

                        time.sleep(self.cfg.input_poll_sleep)

                        continue

                    if message.type != "note_on":
                        continue

                    if message.velocity == 0:
                        continue

                    self.raw_queue.put((time.monotonic(), message.note))

        except Exception as exc:

            print("MIDI INPUT ERROR:", repr(exc))

            self.running = False

    def aggregate(self):

        pending = None

        while self.running:

            try:

                if pending is not None:

                    timestamp, pitch = pending
                    pending = None

                else:

                    timestamp, pitch = self.raw_queue.get(
                        timeout=self.cfg.input_queue_timeout
                    )

            except queue.Empty:
                continue

            pitches = {pitch}

            deadline = timestamp + self.cfg.grouping_window

            while self.running:

                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    break

                try:

                    next_event = self.raw_queue.get(timeout=remaining)

                except queue.Empty:
                    break

                next_timestamp, next_pitch = next_event

                if next_timestamp <= deadline:

                    pitches.add(next_pitch)

                else:

                    pending = next_event
                    break

            self.event_queue.put(
                InputEvent(timestamp=timestamp, pitches=frozenset(pitches))
            )

    def get_events(self):

        events = []

        while True:

            try:

                events.append(self.event_queue.get_nowait())

            except queue.Empty:
                break

        return events

    def stop(self):

        self.running = False

        for thread in (self.listener_thread, self.aggregator_thread):

            if thread and thread.is_alive():

                thread.join(timeout=2.0)


# ============================================================
# SCORE FOLLOWER
# ============================================================


class ScoreFollower:

    def __init__(self, score, cfg):

        self.score = score
        self.cfg = cfg

        self.n = len(score.events)

        self.history = deque()

        self.max_history_seconds = score.history_window_seconds(cfg)

        self.pitch_masks = np.array(
            [pitches_to_mask(event.pitches) for event in score.events], dtype=np.int32
        )

        self.pitch_masks = np.ascontiguousarray(self.pitch_masks)

    def reset(self):
        self.history.clear()

    def update(self, event, preferred_position=None):

        self.history.append(event)

        cutoff = event.timestamp - self.max_history_seconds

        while self.history and self.history[0].timestamp < cutoff:

            self.history.popleft()

        observed = list(self.history)

        if len(observed) < self.cfg.min_history:

            return None, observed

        return (self.align(observed, preferred_position), observed)

    def rhythm_analysis(self, observed, pairs):

        cfg = self.cfg

        ratios = []

        for k in range(1, len(pairs)):

            pi, ps = pairs[k - 1]
            ci, cs = pairs[k]

            input_delta = observed[ci].timestamp - observed[pi].timestamp

            score_delta = self.score.score_time_for_index(
                cs
            ) - self.score.score_time_for_index(ps)

            if input_delta <= cfg.min_input_interval or score_delta <= 0:
                continue

            ratio = score_delta / input_delta

            if cfg.min_playback_speed <= ratio <= cfg.max_playback_speed:

                ratios.append(ratio)

        if len(ratios) < 2:
            return 1.0, 0.5

        median_ratio = statistics.median(ratios)

        deviations = [abs(math.log(r / median_ratio)) for r in ratios]

        rhythm_score = math.exp(
            -statistics.median(deviations)
            / max(cfg.rhythm_sigma, 0.001)
            * cfg.rhythm_sigma
        )

        return median_ratio, rhythm_score

    def align_from(self, observed_masks, observed, start, length, endpoint, cost):

        cfg = self.cfg

        trace = build_traceback(
            observed_masks,
            self.pitch_masks,
            start,
            length,
            cfg.insertion_cost,
            cfg.deletion_cost,
            cfg.pitch_distance_sigma,
        )

        i = len(observed)
        j = endpoint

        pairs = []

        while i > 0 and j >= 0:

            operation = trace[i, j]

            if operation == 0:

                pairs.append((i - 1, start + j - 1))

                i -= 1
                j -= 1

            elif operation == 1:

                i -= 1

            elif operation == 2:

                j -= 1

            else:
                break

        pairs.reverse()

        if not pairs:
            return None

        position = pairs[-1][1] % self.n

        tempo_ratio, rhythm_score = self.rhythm_analysis(observed, pairs)

        matched_fraction = len(pairs) / len(observed)

        combined_cost = cost + cfg.rhythm_weight * (1.0 - rhythm_score)

        confidence = math.exp(-2.0 * combined_cost) * matched_fraction

        return MatchResult(
            position=position,
            confidence=confidence,
            cost=combined_cost,
            matched_events=len(pairs),
            matched_pairs=pairs,
            tempo_ratio=tempo_ratio,
            rhythm_score=rhythm_score,
        )

    def align(self, observed, preferred_position=None):

        cfg = self.cfg

        n = len(observed)

        if n < cfg.min_history:
            return None

        length = min(
            max(n * cfg.max_alignment_multiplier, n + cfg.max_alignment_extra), self.n
        )

        observed_masks = np.fromiter(
            (pitches_to_mask(event.pitches) for event in observed),
            dtype=np.int32,
            count=n,
        )

        observed_masks = np.ascontiguousarray(observed_masks)

        starts = np.arange(self.n, dtype=np.int32)

        costs, endpoints = evaluate_candidates(
            observed_masks,
            self.pitch_masks,
            starts,
            length,
            cfg.insertion_cost,
            cfg.deletion_cost,
            cfg.pitch_distance_sigma,
        )

        # Candidate search.
        #
        # Restrict traceback to a shortlist, rather than
        # reconstructing every possible alignment.

        order = np.argsort(costs)

        if cfg.candidate_limit > 0:

            order = order[: cfg.candidate_limit]

        best_cost = float(costs[order[0]])

        ambiguity_limit = best_cost + cfg.ambiguity_cost_margin

        candidates = []

        for candidate_index in order:

            candidate_cost = float(costs[candidate_index])

            if candidate_cost > ambiguity_limit:
                break

            start = int(starts[candidate_index])

            endpoint = int(endpoints[candidate_index])

            position = (start + endpoint - 1) % self.n

            distance = 0.0

            if preferred_position is not None:

                distance = self.score.beat_distance(position, preferred_position)

            candidates.append((candidate_index, position, candidate_cost, distance))

        if not candidates:
            return None

        # ------------------------------------------------
        # DUPLICATE SECTION RESOLUTION
        # ------------------------------------------------

        # When passages have similar alignment costs,
        # prefer the candidate nearest to the predicted
        # playback position.
        #
        # Musical evidence still takes priority when
        # the cost difference exceeds the ambiguity margin.

        if preferred_position is not None:

            selected = min(
                candidates, key=lambda item: (item[3] * cfg.continuity_weight, item[2])
            )

        else:

            selected = candidates[0]

        candidate_index = selected[0]

        start = int(starts[candidate_index])

        endpoint = int(endpoints[candidate_index])

        cost = float(costs[candidate_index])

        return self.align_from(observed_masks, observed, start, length, endpoint, cost)


# ============================================================
# TEMPO ESTIMATOR
# ============================================================


class TempoEstimator:

    def __init__(self, cfg):

        self.cfg = cfg

        self.history = deque(maxlen=cfg.tempo_history_size)

        self.speed_ratio = 1.0

    def reset(self):

        self.history.clear()
        self.speed_ratio = 1.0

    def update(self, result):

        cfg = self.cfg

        if result is None:
            return self.speed_ratio

        if result.matched_events < cfg.min_tempo_matches:
            return self.speed_ratio

        if result.rhythm_score < cfg.min_tempo_rhythm_score:
            return self.speed_ratio

        self.history.append(result.tempo_ratio)

        stable = statistics.median(self.history)

        self.speed_ratio = (
            cfg.tempo_smoothing * stable
            + (1.0 - cfg.tempo_smoothing) * self.speed_ratio
        )

        return max(
            cfg.min_playback_speed, min(cfg.max_playback_speed, self.speed_ratio)
        )


# ============================================================
# METRICAL TRACKER
# ============================================================


class MetricalTracker:

    def __init__(self, score, cfg):

        self.score = score
        self.cfg = cfg

        self.evidence = deque()

        self.last_input_time = None
        self.current_beat = 0.0

        self.estimated_seconds_per_beat = cfg.initial_seconds_per_beat

    def reset(self):

        self.evidence.clear()

        self.last_input_time = None
        self.current_beat = 0.0

        self.estimated_seconds_per_beat = self.cfg.initial_seconds_per_beat

    def update_clock(self, timestamp):

        if self.last_input_time is None:

            self.last_input_time = timestamp
            return

        delta = max(0.0, timestamp - self.last_input_time)

        self.last_input_time = timestamp

        self.current_beat += delta / max(self.estimated_seconds_per_beat, 0.05)

    def update_tempo(self, result):

        if result is None:
            return

        cfg = self.cfg

        if result.rhythm_score < cfg.min_tempo_rhythm_score:
            return

        index = result.position

        duration = self.score.events[index].duration

        if duration <= 0:
            return

        expected_duration = self.score.event_durations_seconds[index]

        if expected_duration <= 0:
            return

        candidate = expected_duration / duration

        smoothing = cfg.metrical_tempo_smoothing

        self.estimated_seconds_per_beat = (
            smoothing * candidate + (1.0 - smoothing) * self.estimated_seconds_per_beat
        )

    def add(self, timestamp, result, matched):

        cfg = self.cfg

        self.update_clock(timestamp)

        if result is not None:
            self.update_tempo(result)

        self.evidence.append(
            Evidence(
                timestamp=timestamp,
                beat=self.current_beat,
                confidence=(result.confidence if result else 0.0),
                position=(result.position if result else -1),
                matched=matched,
            )
        )

        cutoff = self.current_beat - cfg.evidence_window_beats

        while self.evidence and self.evidence[0].beat < cutoff:

            self.evidence.popleft()

    def summary(self):

        matched = [item for item in self.evidence if item.matched]

        if not matched:
            return 0.0, 0, 0.0

        confidence = statistics.mean(item.confidence for item in matched)

        span = self.evidence[-1].beat - self.evidence[0].beat

        return confidence, len(matched), span

    def is_reliable(self):

        cfg = self.cfg

        confidence, matches, span = self.summary()

        return (
            matches >= cfg.min_evidence_matches
            and span >= cfg.min_evidence_span
            and confidence >= cfg.confidence_threshold
        )


# ============================================================
# MIDI PLAYBACK
# ============================================================


class MIDIPlayback:

    def __init__(self, score, output_port, cfg):

        self.score = score
        self.output_port = output_port
        self.cfg = cfg

        self.commands = queue.Queue()

        self.running = False
        self.thread = None

        self.current_position = None

        self.position_lock = threading.Lock()
        self.state_lock = threading.Lock()

        self.speed_ratio = 1.0

        self.anchor_wall = None
        self.anchor_score = 0.0

    def start(self, position, speed=1.0):

        with self.state_lock:

            if self.running:
                return False

            if self.thread and self.thread.is_alive():

                self.thread.join(timeout=self.cfg.thread_join_timeout)

                if self.thread.is_alive():
                    return False

            self.commands = queue.Queue()

            self.speed_ratio = max(
                self.cfg.min_playback_speed, min(self.cfg.max_playback_speed, speed)
            )

            self.running = True

            self.commands.put(("seek", position))

            self.thread = threading.Thread(target=self.play, daemon=False)

            self.thread.start()

            return True

    def set_speed(self, ratio):

        if self.running:

            ratio = max(
                self.cfg.min_playback_speed, min(self.cfg.max_playback_speed, ratio)
            )

            self.commands.put(("speed", ratio))

    def get_current_position(self):

        with self.position_lock:
            return self.current_position

    def position_at(self, timestamp):

        with self.position_lock:

            if self.anchor_wall is None:
                return None

            elapsed = (timestamp - self.anchor_wall) * self.speed_ratio

            target_time = self.anchor_score + elapsed

            loop_duration = self.score.loop_duration

            if loop_duration <= 0:
                return None

            local_time = target_time % loop_duration

            index = np.searchsorted(self.score.event_times, local_time, side="left")

            return min(max(0, int(index) - 1), len(self.score.events) - 1)

    def stop(self):

        with self.state_lock:

            if not self.running:
                return

            print("Stopping playback...")

            self.commands.put(("stop", None))

            if self.thread and self.thread.is_alive():

                self.thread.join(timeout=self.cfg.thread_join_timeout)

            if self.thread and self.thread.is_alive():

                print("ERROR: Playback thread did not terminate.")

                return

            self.running = False

            with self.position_lock:

                self.current_position = None
                self.anchor_wall = None

    def play(self):

        cfg = self.cfg

        active_notes = set()
        note_offs = []

        port = None

        try:

            port = mido.open_output(self.output_port)

            n = len(self.score.events)

            loop_duration = self.score.loop_duration

            event_index = 0
            cycle = 0

            anchor_wall = time.monotonic()
            anchor_score = 0.0

            def release_all():

                for pitch in list(active_notes):

                    try:

                        port.send(mido.Message("note_off", note=pitch, velocity=0))

                    except Exception:
                        pass

                active_notes.clear()
                note_offs.clear()

            def initialize(position):

                nonlocal event_index
                nonlocal cycle
                nonlocal anchor_wall
                nonlocal anchor_score

                event_index = position % n
                cycle = 0

                anchor_score = self.score.event_time(event_index)

                anchor_wall = time.monotonic()

                with self.position_lock:

                    self.current_position = event_index
                    self.anchor_wall = anchor_wall
                    self.anchor_score = anchor_score

                print(
                    "PLAYING FROM:", event_index, "| speed:", round(self.speed_ratio, 2)
                )

            command, value = self.commands.get()

            if command == "stop":
                return

            initialize(value)

            while self.running:

                while True:

                    try:

                        command, value = self.commands.get_nowait()

                    except queue.Empty:
                        break

                    if command == "stop":

                        release_all()
                        self.running = False
                        break

                    if command == "seek":

                        release_all()
                        initialize(value)

                    elif command == "speed":

                        now = time.monotonic()

                        anchor_score += (now - anchor_wall) * self.speed_ratio

                        anchor_wall = now
                        self.speed_ratio = value

                        with self.position_lock:

                            self.anchor_wall = anchor_wall
                            self.anchor_score = anchor_score

                if not self.running:
                    break

                now = time.monotonic()

                musical_now = anchor_score + (now - anchor_wall) * self.speed_ratio

                while note_offs and note_offs[0][0] <= musical_now:

                    _, pitch = heapq.heappop(note_offs)

                    if pitch in active_notes:

                        port.send(mido.Message("note_off", note=pitch, velocity=0))

                        active_notes.discard(pitch)

                event = self.score.events[event_index]

                event_time = cycle * loop_duration + self.score.event_time(event_index)

                target_wall = (
                    anchor_wall + (event_time - anchor_score) / self.speed_ratio
                )

                remaining = target_wall - now

                if remaining > 0:

                    time.sleep(min(remaining, cfg.scheduler_sleep))

                    continue

                duration = max(
                    self.score.event_durations_seconds[event_index],
                    cfg.minimum_note_duration,
                )

                for pitch in event.pitches:

                    port.send(
                        mido.Message("note_on", note=pitch, velocity=cfg.midi_velocity)
                    )

                    active_notes.add(pitch)

                    heapq.heappush(note_offs, (event_time + duration, pitch))

                with self.position_lock:

                    self.current_position = event_index

                event_index += 1

                if event_index >= n:

                    event_index = 0
                    cycle += 1

        except Exception as exc:

            print("PLAYBACK ERROR:", repr(exc))

        finally:

            if port is not None:

                try:

                    release_all()
                    port.close()

                except Exception as exc:

                    print("MIDI cleanup warning:", repr(exc))

            self.running = False

            with self.position_lock:

                self.current_position = None
                self.anchor_wall = None

            print("Playback stopped.")


# ============================================================
# APPLICATION
# ============================================================


class Application:

    def __init__(self, filename, input_port, output_port, cfg):

        self.cfg = cfg

        self.score = Score(filename)

        self.midi_input = MIDIInput(input_port, cfg)

        self.follower = ScoreFollower(self.score, cfg)

        self.tempo = TempoEstimator(cfg)

        self.tracker = MetricalTracker(self.score, cfg)

        self.playback = MIDIPlayback(self.score, output_port, cfg)

        self.playback_started = False

        self.mode = "SEARCHING"

        self.bad_beats = 0.0

        self.last_tempo_update = 0.0

        self.alternative_position = None

        self.last_mismatch_timestamp = None

    def reset_search(self):

        self.follower.reset()
        self.tempo.reset()
        self.tracker.reset()

        self.bad_beats = 0.0

        self.alternative_position = None
        self.last_mismatch_timestamp = None

    def start_playback(self, result):

        speed = self.tempo.update(result)

        print("\n================================")
        print("SCORE POSITION CONFIRMED")
        print("Position:", result.position)
        print("Confidence:", round(result.confidence, 3))
        print("Tempo ratio:", round(speed, 3))
        print("================================")

        if not self.playback.start(result.position, speed):
            return

        self.playback_started = True
        self.mode = "PLAYING"

        self.bad_beats = 0.0

    def acquire(self, result, timestamp):

        cfg = self.cfg

        if result.confidence < cfg.acquisition_confidence_threshold:
            return

        self.tracker.add(timestamp, result, matched=True)

        confidence, matches, span = self.tracker.summary()

        if self.tracker.is_reliable():

            print(
                "ACQUISITION:",
                "confidence:",
                round(confidence, 3),
                "matches:",
                matches,
                "metrical span:",
                round(span, 2),
            )

            self.start_playback(result)

    def monitor_position(self, result, timestamp):

        cfg = self.cfg

        expected_position = self.playback.position_at(timestamp)

        if expected_position is None:
            return

        if result is None:

            self.tracker.add(timestamp, None, matched=False)

            return

        distance = self.score.beat_distance(result.position, expected_position)

        matched = (
            result.confidence >= cfg.confidence_threshold
            and distance <= cfg.mismatch_distance
        )

        self.tracker.add(timestamp, result, matched)

        if matched:

            self.bad_beats = max(0.0, self.bad_beats - 0.5)

            self.alternative_position = None
            self.last_mismatch_timestamp = None

            speed = self.tempo.update(result)

            now = time.monotonic()

            if now - self.last_tempo_update > cfg.playback_speed_update_interval:

                self.playback.set_speed(speed)

                self.last_tempo_update = now

            return

        if result.confidence < cfg.confidence_threshold:
            return

        if cfg.verbose:

            print(
                "ALTERNATIVE POSITION:",
                result.position,
                "| expected:",
                expected_position,
                "| confidence:",
                round(result.confidence, 3),
            )

        if self.alternative_position is None:

            self.alternative_position = result.position
            self.last_mismatch_timestamp = timestamp

            return

        alternative_distance = self.score.beat_distance(
            result.position, self.alternative_position
        )

        if alternative_distance > (cfg.position_change_margin * 8):

            self.alternative_position = result.position
            self.last_mismatch_timestamp = timestamp

            return

        if self.last_mismatch_timestamp is not None:

            delta = max(0.0, timestamp - self.last_mismatch_timestamp)

            self.bad_beats += delta / max(self.tracker.estimated_seconds_per_beat, 0.05)

        self.last_mismatch_timestamp = timestamp

        if self.bad_beats < cfg.mismatch_duration_beats:
            return

        print("\n================================")
        print("NEW SCORE POSITION CONFIRMED")
        print("Stopping playback.")
        print("Reacquiring alignment.")
        print("================================")

        self.playback.stop()

        self.playback_started = False
        self.mode = "REACQUIRING"

        self.reset_search()

    def run(self):

        cfg = self.cfg

        print("\n================================")
        print("REAL-TIME SCORE FOLLOWER")
        print("================================")

        print("Score events:", len(self.score.events))
        print("Confidence:", cfg.confidence_threshold)
        print("History bars:", cfg.history_bars)
        print("Minimum history:", cfg.min_history)
        print("Numba:", NUMBA_AVAILABLE)
        print("Ambiguity margin:", cfg.ambiguity_cost_margin)
        print("Continuity weight:", cfg.continuity_weight)

        print("\nWaiting for MIDI input...")

        self.midi_input.start()

        try:

            while True:

                events = self.midi_input.get_events()

                if not events:

                    time.sleep(cfg.main_loop_sleep)
                    continue

                for input_event in events:

                    preferred_position = None

                    if self.playback_started:

                        preferred_position = self.playback.position_at(
                            input_event.timestamp
                        )

                    result, _ = self.follower.update(
                        input_event, preferred_position=preferred_position
                    )

                    if result is None:
                        continue

                    if cfg.verbose:

                        print(
                            "MATCH:",
                            result.position,
                            "| confidence:",
                            round(result.confidence, 3),
                            "| rhythm:",
                            round(result.rhythm_score, 3),
                        )

                    if not self.playback_started:

                        self.acquire(result, input_event.timestamp)

                        continue

                    self.monitor_position(result, input_event.timestamp)

        except KeyboardInterrupt:

            print("\nStopping...")

        finally:

            self.midi_input.stop()
            self.playback.stop()

            print("Application stopped.")


# ============================================================
# CLI
# ============================================================


def add_argument(parser, name, default, arg_type=None, help_text=None):

    parser.add_argument(
        "--" + name.replace("_", "-"),
        type=arg_type or type(default),
        default=default,
        help=(f"{help_text or name} (default: {default})"),
    )


def build_parser():

    parser = argparse.ArgumentParser(
        description=(
            "Fully configurable, Numba-accelerated " "real-time MIDI score follower"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("score", nargs="?")

    parser.add_argument("--input")
    parser.add_argument("--output")

    parser.add_argument("--list-ports", action="store_true")

    # All Config fields are exposed automatically.

    defaults = Config()

    for name, default in vars(defaults).items():

        if isinstance(default, bool):

            parser.add_argument(
                "--" + name.replace("_", "-"),
                action=("store_false" if default else "store_true"),
                default=default,
                help=f"Toggle {name}",
            )

        else:

            add_argument(parser, name, default)

    return parser


def validate_config(cfg, parser):

    positive = [
        "grouping_window",
        "input_poll_sleep",
        "input_queue_timeout",
        "main_loop_sleep",
        "min_history",
        "pitch_distance_sigma",
        "rhythm_sigma",
        "tempo_history_size",
        "min_playback_speed",
        "max_playback_speed",
        "scheduler_sleep",
        "thread_join_timeout",
        "minimum_note_duration",
        "initial_seconds_per_beat",
    ]

    for name in positive:

        if getattr(cfg, name) <= 0:

            parser.error(f"--{name.replace('_', '-')} must be positive")

    if cfg.max_playback_speed < cfg.min_playback_speed:
        parser.error("Maximum playback speed must be >= minimum.")

    if cfg.min_history < 1:
        parser.error("Minimum history must be >= 1.")

    if cfg.history_bars < 1:
        parser.error("History bars must be >= 1.")

    if cfg.candidate_limit < 0:
        parser.error("Candidate limit must be >= 0.")

    if cfg.midi_velocity < 1 or cfg.midi_velocity > 127:
        parser.error("MIDI velocity must be between 1 and 127.")

    if not 0 <= cfg.confidence_threshold <= 1:
        parser.error("Confidence threshold must be between 0 and 1.")

    if not 0 <= cfg.acquisition_confidence_threshold <= 1:
        parser.error("Acquisition threshold must be between 0 and 1.")

    if not 0 <= cfg.tempo_smoothing <= 1:
        parser.error("Tempo smoothing must be between 0 and 1.")

    if not 0 <= cfg.metrical_tempo_smoothing <= 1:
        parser.error("Metrical tempo smoothing must be between 0 and 1.")

    if cfg.insertion_cost < 0 or cfg.deletion_cost < 0:
        parser.error("Alignment costs cannot be negative.")

    if cfg.ambiguity_cost_margin < 0:
        parser.error("Ambiguity margin cannot be negative.")


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


# ============================================================
# MAIN
# ============================================================


def main():

    parser = build_parser()

    args = parser.parse_args()

    if args.list_ports:

        list_ports()
        return

    if not args.score:
        parser.error("Score file required.")

    if not args.input:
        parser.error("--input required.")

    if not args.output:
        parser.error("--output required.")

    cfg = Config(**{name: getattr(args, name) for name in vars(Config())})

    validate_config(cfg, parser)

    app = Application(
        filename=args.score, input_port=args.input, output_port=args.output, cfg=cfg
    )

    app.run()


if __name__ == "__main__":
    main()
