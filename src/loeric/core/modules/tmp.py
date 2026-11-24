import math
import time
from typing import Literal

import pydantic as pdt

import loeric.core.context as lctx
import loeric.core.element as le
import loeric.core.modules.base as lmb


class SynchroniserModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`SynchroniserModule`.

    :param stop_if_unknown: stop playing when the tracker loses the performer.
    :param wait_for_start: do not play until the performer has been found.
    :param fix_threshold: sync errors (eighth notes) below this are ignored;
        above it the tempo is bent to catch up.
    :param stop_threshold: sync errors (eighth notes) above this stop the
        system, which restarts at the next song position of the performer.
    :param audible_delay: eighth notes between the performance clock seen by
        the modules and what is audible: the lookahead of the groover.
    """

    type: Literal["synchroniser"]
    stop_if_unknown: bool
    wait_for_start: bool
    fix_threshold: float = pdt.Field(gt=0.0)
    stop_threshold: float = pdt.Field(gt=0.0)
    audible_delay: float = pdt.Field(default=0.0, ge=0.0)


class SynchroniserModule(lmb.LOERICModule):
    """Keeps the performance in sync with the performer.

    It goes at the END of the pipeline, after the score tracker, and consumes
    its messages. Everything is measured in eighth notes of score time: the
    sync error is how far the audible performance is ahead (positive) or
    behind (negative) the performer, now.

    - ``|error| < fix_threshold``: ignored;
    - ``fix_threshold <= |error| < stop_threshold``: the tempo is bent so that
      the error is gone at a song position, then it goes back to normal;
    - ``|error| >= stop_threshold``: the system stops, jumps to the first song
      position after the performer and starts when the performer gets there.

    ``UserPlayback.position`` must be a fractional song position index:
    ``song_position + song_offset / sync_interval``.
    """

    config_class = SynchroniserModuleConfig

    # limits of the tempo bend, relative to the normal tempo
    _MIN_RATIO = 0.5
    _MAX_RATIO = 2.0
    # tempo bends changing less than this are not sent again
    _RATIO_EPSILON = 0.01
    # restart waits shorter than this (seconds) target the following position
    _MIN_RESTART_WAIT = 0.25
    # seconds after a start in which the error is not checked
    _SETTLE_SECONDS = 1.0

    def __init__(
        self,
        stop_if_unknown: bool,
        wait_for_start: bool,
        fix_threshold: float,
        stop_threshold: float,
        audible_delay: float = 0.0,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if stop_threshold <= fix_threshold:
            raise ValueError("stop_threshold must be larger than fix_threshold.")

        self._name = "synchroniser"
        self._is_online = True

        self._stop_if_unknown = stop_if_unknown
        self._fix_threshold = fix_threshold
        self._stop_threshold = stop_threshold
        self._audible_delay = audible_delay

        # from the tune, on the first element
        self._interval = None  # eighths between song positions
        self._origin = None  # score time of song position 0, eighths
        self._first_qpm = None

        # whether the performance is allowed to play
        self._stopped = wait_for_start

        # latest tracked position as (score time in eighths, wall time)
        self._last_user_position = None
        # a restart is planned: song position to seek to and when to start
        self._seek_target = None
        self._wake_up_at = None
        # tempo bend: ratio to the normal tempo and song position time to reach
        self._ratio = 1.0
        self._bend_target = None

    # --------------------------------------------------------
    # PROCESS
    # --------------------------------------------------------

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Turn the position of the performer into playback commands."""
        if self._interval is not None:
            return

        tune = lctx.CurrentTune.get()

        self._interval = float(tune.sync_interval.eighth_duration)
        self._origin = float(tune._position_times[0])
        self._first_qpm = float(tune.tempos[0].qpm)

        now = time.perf_counter()
        out = []

        # the planned restart is due
        if self._wake_up_at is not None and now >= self._wake_up_at:
            out.extend(self._start(now))

        if isinstance(element, le.SongPosition):
            out.append(element)

        elif isinstance(element, le.UnknownUserPosition):
            out.extend(self._on_unknown())

        elif isinstance(element, le.UserPlayback):
            out.extend(self._on_playback(element, now))

        elif not self._stopped:
            out.append(element)

        return out

    def _on_unknown(self):
        self._last_user_position = None
        self._wake_up_at = None
        self._seek_target = None

        if self._stop_if_unknown:
            return self._reset_ratio() + self._stop()

        return []

    def _on_playback(self, element: le.UserPlayback, now: float):
        self._last_user_position = (
            self._origin + element.position * self._interval,
            element.timestamp,
        )

        # not playing: (re)plan where and when to start
        if self._stopped:
            return self._hard_fix(now)

        error = self._system_position() - self._user_now(now)

        if abs(error) >= self._stop_threshold:
            return self._reset_ratio() + self._stop() + self._hard_fix(now)

        return self._soft_fix(error)

    # --------------------------------------------------------
    # FIXES
    # --------------------------------------------------------

    def _soft_fix(self, error: float):
        """Bend the tempo to be in sync at a song position, then go back."""
        if self._ratio == 1.0 and abs(error) < self._fix_threshold:
            return []

        # settled: back to the normal tempo
        if self._ratio != 1.0 and abs(error) <= 0.5 * self._fix_threshold:
            return self._reset_ratio()

        position = self._system_position()

        # aim at a song position that is far enough; once reached, at the next
        if self._bend_target is None or position >= self._bend_target:
            score_time = position + 0.5 * self._interval
            index = math.ceil((score_time - self._origin) / self._interval)
            return self._origin + index * self._interval

        # distance the system covers while the error is removed: if the
        # system is ahead by `error`, it covers `distance` while the performer
        # covers `distance - error`
        distance = self._bend_target - position
        needed = distance + error

        ratio = distance / needed if needed > 0 else self._MAX_RATIO
        ratio = min(max(ratio, self._MIN_RATIO), self._MAX_RATIO)

        if abs(ratio - self._ratio) < self._RATIO_EPSILON:
            return []

        return self._set_ratio(ratio)

    def _hard_fix(self, now: float):
        """Seek to the next song position of the performer, start there."""
        user_now = self._user_now(now)
        seconds_per_eighth = self._seconds_per_eighth()

        marker = self._seek_target

        # keep the planned song position, unless the performer went past it
        if marker is None or self._origin + marker * self._interval <= user_now:
            marker = math.floor((user_now - self._origin) / self._interval) + 1

            # not too close: the restart needs some time
            while (
                self._origin + marker * self._interval - user_now
            ) * seconds_per_eighth < self._MIN_RESTART_WAIT:
                marker += 1

        out = []

        if marker != self._seek_target:
            self._seek_target = marker
            out.append(le.SeekPosition(position=marker))

        arrival = self._origin + marker * self._interval - user_now
        self._wake_up_at = now + arrival * seconds_per_eighth

        return out

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    def _start(self, now: float):
        self._stopped = False
        self._wake_up_at = None
        self._seek_target = None

        return [le.StartPlayback()]

    def _stop(self):
        if self._stopped:
            return []

        self._stopped = True

        return [le.StopPlayback()]

    def _set_ratio(self, ratio: float):
        self._ratio = ratio

        return [
            le.UserTempo(
                qpm=self._first_qpm * ratio,
                time=lctx.PerformanceClock.now(),
            )
        ]

    def _reset_ratio(self):
        self._bend_target = None

        return [] if self._ratio == 1.0 else self._set_ratio(1.0)

    # --------------------------------------------------------
    # MEASURES, in eighths of score time unless said otherwise
    # --------------------------------------------------------

    def _seconds_per_eighth(self) -> float:
        """Seconds per eighth of the performer, assumed at the normal tempo."""
        qpm = self._first_qpm if self._tempo is None else float(self._tempo.qpm)

        return 30.0 / qpm * self._ratio

    def _system_position(self) -> float:
        """Score time that is audible now."""
        return float(lctx.PerformanceClock.now()) - self._audible_delay

    def _user_now(self, now: float) -> float:
        """Score time of the performer now, extrapolated from the last match."""
        position, timestamp = self._last_user_position

        return position + (now - timestamp) / self._seconds_per_eighth()
