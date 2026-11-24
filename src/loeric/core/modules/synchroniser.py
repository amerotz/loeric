import logging
import time
from typing import Literal

import numpy as np

import loeric.core.context as lctx
import loeric.core.element as le
import loeric.core.modules.base as lmb

logger = logging.getLogger(__name__)


class SynchroniserModuleConfig(lmb.BaseModuleConfig):
    """Config for :class:`SynchroniserModule`.

    :param stop_if_unknown: stop playing when the performer is lost.
    :param wait_for_start: do not play until the performer is found.
    :param fix_threshold: sync errors below this (eighth notes) are ignored;
        above it the tempo is bent to catch up.
    :param stop_threshold: sync errors above this (eighth notes) stop the
        system, which restarts at the next song position of the performer.
    :param sync_interval: the interval over which to synchronise, i eighth notes.
    """

    type: Literal["synchroniser"]
    stop_if_unknown: bool
    wait_for_start: bool
    fix_threshold: float
    stop_threshold: float
    sync_interval: float
    use_ms: bool


class SynchroniserModule(lmb.LOERICModule):
    """Keeps the performance in sync with the performer.

    It goes after the score tracker, and consumes
    its messages. Positions are in eighth notes of score time, timestamps in
    seconds from :func:`time.perf_counter`.

    - below ``fix_threshold`` the system is left alone;
    - between the thresholds, the tempo is bent for one sync interval so that
      the system is back in sync at the end of it (a soft fix);
    - above ``stop_threshold``, the system stops, jumps to the next song
      position of the performer and starts when they get there (a hard fix).

    Real time: ``_process`` runs on every tick, so ordinary elements only go
    through a few checks. The work is done when a message arrives, and:

    - what depends on the tune (sync interval, first tempo) is read once;
    - what only changes with a song position (the system timestamp,
      compensated for the lookahead) is computed when the song position
      arrives, not at every playback message;
    - the tempo bend is planned only when needed, and from values at hand;
    - nothing blocks: debug output goes through :mod:`logging`.
    """

    config_class = SynchroniserModuleConfig

    def __init__(
        self,
        stop_if_unknown: bool,
        wait_for_start: bool,
        fix_threshold: float,
        stop_threshold: float,
        sync_interval: float,
        use_ms: bool,
        **kwargs,
    ):

        super().__init__(**kwargs)

        self._name = "synchroniser"

        self._modules = []
        self._is_online = True

        self._stop_if_unknown = stop_if_unknown
        self._wait_for_start = wait_for_start
        self._fix_threshold = fix_threshold
        self._stop_threshold = stop_threshold
        self._sync_interval = sync_interval
        self._use_ms = use_ms

        self._HISTORY_SECONDS = 1

        self._acquired_once = False
        self._stopped = self._wait_for_start

        self._user_positions = []
        self._user_timestamps = []
        self._system_position = None
        self._system_timestamp = None

        self._wake_up_at = None
        self._reset_tempo_at = None

        self._base_qpm = None

        # ask Tune to synchronise
        lctx.CurrentTune.get().synchronise_every(self._sync_interval)

    def _process(
        self,
        element: le.LOERICElement,
        window: list[le.LOERICElement] = None,
    ):
        """Synchronise with incoming playback and position messages.

        :param element: the element to process.
        :param window: unused.
        :return: the elements to pass on, followed by the commands (start,
            stop, seek, tempo) needed to get in sync with the performer.
        """
        out = []
        now = time.perf_counter()
        clock = float(lctx.PerformanceClock.now())

        # the planned restart is due
        if self._wake_up_at is not None:
            if now >= self._wake_up_at:
                out.extend(self._start())

        # reset tempo
        if self._reset_tempo_at is not None:
            if clock >= self._reset_tempo_at:
                out.extend(self._reset_tempo())

        # tempo changes
        if isinstance(element, le.Tempo):
            self._base_qpm = element.qpm

        # record system positions
        elif isinstance(element, le.SongPosition):
            self._handle_system_position(element, now)

        # we don't know where we are
        elif isinstance(element, le.UnknownUserPosition):
            self._handle_unknown_position()
            if self._stop_if_unknown or (
                self._wait_for_start and not self._acquired_once
            ):
                out.extend(self._stop())

        # we are tracking the user
        elif isinstance(element, le.UserPlayback):

            if element.is_jump:
                out.extend(self._stop())

            if self._stopped and self._wake_up_at is None:
                out.extend(self._seek(element.score_time))
                out.extend(self._start())

            self._handle_user_position(element)

        # check synchronisation
        # speed of the performer
        # in eighths per second
        result = self._fit()

        if result is not None and self._base_qpm is not None:

            m, b = result
            qpm = 30 * m

            s_p, s_t = self._system_position, self._system_timestamp
            # check for reasonable tempo
            if s_p is not None and s_t is not None:

                # expected user position at system timestamp
                if self._use_ms:
                    expected = (s_p - b) / m

                    diff = abs(expected - s_t)
                else:
                    expected = m * s_t + b

                    diff = abs(expected - s_p)

                # hard fix
                if diff >= self._stop_threshold:
                    out.extend(
                        self._hard_fix(
                            self._user_positions[-1], self._user_timestamps[-1], m, now
                        )
                    )

                # adjust base line tempo
                else:
                    # a plausible tempo that is not the current one
                    if 0.5 * self._base_qpm <= qpm <= 2 * self._base_qpm:

                        self._base_qpm = qpm
                        out.append(
                            le.UserTempo(
                                qpm=qpm,
                                time=clock + le.ONE_OVER_MINIMUM_QUARTER_DIVISION,
                            )
                        )

                # soft fix
                if self._fix_threshold <= diff < self._stop_threshold:
                    out.extend(
                        self._soft_fix(
                            self._user_positions[-1],
                            self._user_timestamps[-1],
                            m,
                            now,
                            clock,
                        )
                    )

        if not self._stopped and (not self._wait_for_start or self._acquired_once):

            out.append(element)

        return out

    def _hard_fix(self, user_position, user_timestamp, user_speed, now):
        out = []

        if self._wake_up_at is None:

            system_speed = self._base_qpm / 30
            new_position = (
                np.ceil(user_position / self._sync_interval) * self._sync_interval
            )

            new_timestamp = (
                user_timestamp
                + (new_position - user_position) / user_speed
                - self._global_lookahead / system_speed
            )

            while new_timestamp <= now:
                new_position += self._sync_interval
                new_timestamp = (
                    now
                    + (new_position - user_position) / user_speed
                    - self._global_lookahead / system_speed
                )

            out.extend(self._reset_tempo())
            out.extend(self._stop())
            out.extend(self._seek(new_position))

            self._wake_up_at = new_timestamp
            logger.info(f"Hard fix. Waking up at position {new_position}.")

        return out

    def _fit(self):

        if len(self._user_positions) < 2:
            return None

        positions = np.array(self._user_positions)
        timestamps = np.array(self._user_timestamps)

        mean_t = timestamps.mean()
        mean_p = positions.mean()

        dt = timestamps - mean_t

        variance = float(dt @ dt)
        if variance <= 0.0:
            return None
        speed = float(dt @ (positions - mean_p)) / variance
        offset = mean_p - speed * mean_t
        if speed == 0:
            return None

        return speed, offset

    def _handle_user_position(self, element):
        self._acquired_once = True

        # only allow positions
        # aligned with sync interval
        if element.score_time % self._sync_interval != 0:
            return

        self._user_positions.append(element.score_time)
        self._user_timestamps.append(element.timestamp)

        self._user_positions = [
            p
            for t, p in zip(self._user_timestamps, self._user_positions)
            if element.timestamp - t <= self._HISTORY_SECONDS
        ]
        self._user_timestamps = [
            t
            for t in self._user_timestamps
            if element.timestamp - t <= self._HISTORY_SECONDS
        ]

    def _handle_unknown_position(self):
        self._user_positions = []
        self._user_timestamps = []

    def _handle_system_position(self, element, now):
        s_p = element.time.eighth_duration
        s_t = now

        # compensate the lookahead by
        # shifting the system's timestamp in
        # the future.
        s_t += self._global_lookahead * 30 / self._base_qpm

        self._system_position = s_p
        self._system_timestamp = s_t

    def _soft_fix(self, user_position, user_timestamp, user_speed, now, clock):
        out = []
        sync_interval = self._sync_interval

        # one bend at a time
        if self._reset_tempo_at is None:
            # eighths per second of the system, normal tempo
            system_speed = self._base_qpm / 30

            # how far ahead the system is, right now
            user_now = user_position + (now - user_timestamp) * user_speed

            # remove the error over the next interval
            new_position = np.ceil(user_now / sync_interval) * sync_interval

            # the new tempo starts when the audible
            # position reaches the clock
            start_timestamp = now + self._global_lookahead / system_speed
            new_timestamp = now + (new_position - user_now) / user_speed

            while (
                new_position <= self._system_position
                or new_timestamp <= start_timestamp
            ):
                new_position += sync_interval
                new_timestamp = now + (new_position - user_now) / user_speed

            multiplier = (
                (new_position - clock)
                / (new_timestamp - start_timestamp)
                / system_speed
            )
            multiplier = min(max(multiplier, 0.5), 2)

            # tempo changes are anchored to score time:
            # bend it now and bring it back at the end
            out.append(
                le.UserTempo(
                    qpm=self._base_qpm * multiplier,
                    time=clock + le.ONE_OVER_MINIMUM_QUARTER_DIVISION,
                )
            )

            self._reset_tempo_at = new_position
            logger.info(f"Soft fix. Synchronising at position {new_position}.")
        return out

    def _start(self):
        """Start playback.

        :return: the start command.
        """
        self._stopped = False
        self._wake_up_at = None
        self._reset_tempo_at = None

        return [le.StartPlayback()]

    def _stop(self):
        """Stop playback.

        :return: the stop command.
        """
        self._stopped = True
        self._wake_up_at = None
        self._reset_tempo_at = None

        self._system_position = None
        self._system_timestamp = None
        self._user_positions = []
        self._user_timestamps = []

        return [le.StopPlayback()]

    def _reset_tempo(self):
        """Bring the tempo back to normal right away.

        :return: the tempo command, or nothing if the tempo is not bent.
        """
        if self._reset_tempo_at is not None:
            self._reset_tempo_at = None
            return [
                le.UserTempo(
                    qpm=self._base_qpm,
                    time=lctx.PerformanceClock.now()
                    + le.ONE_OVER_MINIMUM_QUARTER_DIVISION,
                )
            ]
        return []

    def _seek(self, position):
        """Move the performance to a position.

        :param position: score time, in eighths.
        :return: the seek command.
        """
        return [le.SeekPosition(position=position)]
