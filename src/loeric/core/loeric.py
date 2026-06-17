import logging
import time

import numpy as np

import loeric.core.contour as cnt
import loeric.core.element as le
import loeric.core.groover as gr
import loeric.core.mapper as mp
import loeric.core.player as pl

logger = logging.getLogger(__name__)


class LOERIC:

    def __init__(self, config: dict):
        self._config = config
        self._player = pl.Player(config["player"])
        self._mapper = mp.Mapper(config["mapper"])
        self._groover = gr.Groover(config["modules"])

        self._tune = None
        self._contour_manager = None

        # for performance
        self._tick = None
        self._finish = False
        self._qpm = 120

    def set_tune(self, tune):
        """Assign a tune to LOERIC and calculate the associated contours."""
        self._tune = tune
        self._contour_manager = cnt.ContourManager(self._config["contours"], tune)

    def set_tempo(self, tempo: int):
        """Set tempo for LOERIC's performance in quarters per minute (QPM). Defaults to 120 QPM."""
        self._qpm = tempo

    def ready(self):
        """Initialise playback."""
        assert (
            self._tune is not None
        ), "No tune to play. First call 'loeric.set_tune(tune)'"

        # init tune related things
        self._groover.init_key_signature(self._tune.key_signatures[0])
        self._groover.init_time_signature(self._tune.time_signatures[0])

        # tempo
        start_time = self._tune.start_time.eighth_duration
        self._groover.set_tempo(self._qpm, start_time)

        # timekeeping
        self._tick = le.TimeDelta(
            eighth_duration=start_time - self._groover.lookahead_size
        )
        time_division = le.TimeDelta(
            eighth_duration=le.ONE_OVER_MINIMUM_QUARTER_DIVISION
        )

        while self._tick < start_time - self._groover.lookahead_size:
            self._finish = self._player.step(
                self._mapper,
                self._contour_manager,
                self._groover,
                self._tune,
                self._tick,
            )
            self._tick += time_division

    def start(self, stop_event=None):
        """Start playback."""
        assert (
            self._tune is not None
        ), "No tune to play. First call 'loeric.set_tune(tune)'"
        assert (
            self._contour_manager is not None
        ), "No contours for current tune. First call 'loeric.set_tune(tune)'"

        time_division = le.TimeDelta(
            eighth_duration=le.ONE_OVER_MINIMUM_QUARTER_DIVISION
        )
        time_division_f = time_division.eighth_duration

        # start actual loop
        while not self._finish:

            if stop_event and stop_event.is_set():
                logger.info("Stop requested")
                break

            start_time = time.perf_counter()

            self._finish = self._player.step(
                self._mapper,
                self._contour_manager,
                self._groover,
                self._tune,
                self._tick,
                null_events=True,
            )

            self._tick += time_division

            # fraction of eight note converted to seconds
            wait_time = time_division_f * self._player.eighth_duration_seconds

            # compensate loop duration
            delay_time = time.perf_counter() - start_time
            if delay_time > wait_time:
                logger.warning(
                    f"Computation ({np.round(delay_time,4)}s) is taking more than time interval ({np.round(wait_time,4)}s)!"
                )

            wait_time -= delay_time
            # cannot wait negative time
            time.sleep(max(wait_time, 0))

    def reset(self):
        """Reset LOERIC."""
        self._player.reset()
        self._mapper.reset()
        self._groover.reset()

        self._tune = None
        self._contour_manager = None

        # for performance
        self._tick = None
        self._finish = False
        self._qpm = 120

    @property
    def contour_manager(self):
        return self._contour_manager
