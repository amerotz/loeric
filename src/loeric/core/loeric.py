import logging
import multiprocessing
import threading
import time
import traceback

import numpy as np

import loeric.core.contour as cnt
import loeric.core.element as le
import loeric.core.groover as gr
import loeric.core.mapper as mp
import loeric.core.player as pl

logger = logging.getLogger(__name__)


class LOERIC:

    def __init__(self, config: dict, mode: str = "process"):

        assert mode in ["process", "thread"]
        self._mode = mode
        self._config = config
        self._tune = None
        self._tune_type = None

        # for performance
        self._qpm = 120

        self._process = None

        if self._mode == "process":
            self._stop_event = multiprocessing.Event()
        else:
            self._stop_event = threading.Event()

    def set_tune(self, tune):
        """Assign a tune to LOERIC and calculate the associated contours."""
        self._tune = tune

    @staticmethod
    def infer_tune_type(tune):
        """Infer tune type from the tune's time signature."""
        tunes = {
            "2/2": "reel",
            "2/4": "polka",
            "3/4": "waltz",
            "4/4": "hornpipe",
            "6/8": "jig",
            "9/8": "slipjig",
            "12/8": "slide",
        }
        return tunes[tune.time_signatures[0].meter_string]

    def set_tempo(self, tempo: int):
        """Set tempo for LOERIC's performance in quarters per minute (QPM). Defaults to 120 QPM."""
        self._qpm = tempo

    def start(self, wait_for_prompt=False):
        """Start LOERIC in a new process."""
        # event to stop playback
        self._stop_event.clear()

        if self._mode == "process":
            # event to start playback if wait for prompt
            start_event = multiprocessing.Event()
            # event to signal ready state
            ready_event = multiprocessing.Event()
            self._process = multiprocessing.Process(
                target=self._run,
                args=(
                    self._config,
                    self._tune,
                    self._qpm,
                    wait_for_prompt,
                    start_event,
                    ready_event,
                    self._stop_event,
                    self._mode,
                ),
            )
        else:
            start_event = threading.Event()
            ready_event = threading.Event()
            self._process = threading.Thread(
                target=self._run,
                args=(
                    self._config,
                    self._tune,
                    self._qpm,
                    wait_for_prompt,
                    start_event,
                    ready_event,
                    self._stop_event,
                    self._mode,
                ),
            )

        start_event.clear()
        ready_event.clear()

        self._process.start()

        if wait_for_prompt:
            ready_event.wait()
            input("Press any key to start...")

        start_event.set()

    def stop(self):
        """Stop the LOERIC process."""
        if self._process is not None:
            while self._process.is_alive():
                self._stop_event.set()
                self._process.join()
            self._process = None

    def join(self, timeout=None):
        """Wait for the LOERIC process to complete."""
        if self._process and self._process.is_alive():
            self._process.join(timeout)

    @staticmethod
    def _run(
        config, tune, qpm, wait_for_prompt, start_event, ready_event, stop_event, mode
    ):
        """Create all LOERIC objects and start playback."""
        if mode == "process":
            import signal

            signal.signal(signal.SIGINT, signal.SIG_IGN)

        assert tune is not None, "No tune to play. First call 'loeric.set_tune(tune)'"

        ########## INIT THINGS ###############

        contour_manager = cnt.ContourManager(config["contours"], tune)
        mapper = mp.Mapper(config["mapper"])
        groover = gr.Groover(config["modules"])
        player = pl.Player(config["player"])

        # init tune related things
        groover.init_key_signature(tune.key_signatures[0])
        groover.init_time_signature(tune.time_signatures[0])

        # tempo
        start_time = tune.start_time.eighth_duration
        groover.set_tempo(qpm, start_time)

        # timekeeping
        tick = le.TimeDelta(eighth_duration=start_time - groover.lookahead_size)
        time_division = le.TimeDelta(
            eighth_duration=le.ONE_OVER_MINIMUM_QUARTER_DIVISION
        )
        time_division_f = time_division.eighth_duration

        ########## READY PLAYBACK ###############

        try:
            # run in advance until lookahead is reached
            while tick < start_time - groover.lookahead_size:
                finish = player.step(
                    mapper,
                    contour_manager,
                    groover,
                    tune,
                    tick,
                )
                tick += time_division

            ########## WAIT FOR PROMPT ###############

            ready_event.set()
            if wait_for_prompt:
                start_event.wait()

            ########## PLAY ###############

            # start actual loop
            finish = False
            while not finish:

                if stop_event.is_set():
                    logger.info("Stop requested")
                    break

                start_time = time.perf_counter()

                # step
                finish = player.step(
                    mapper,
                    contour_manager,
                    groover,
                    tune,
                    tick,
                    null_events=True,
                )

                tick += time_division

                # fraction of eight note converted to seconds
                wait_time = time_division_f * player.eighth_duration_seconds

                # compensate loop duration
                delay_time = time.perf_counter() - start_time
                if delay_time > wait_time:
                    logger.warning(
                        f"Computation ({np.round(delay_time,4)}s) is taking more than time interval ({np.round(wait_time,4)}s)!"
                    )

                wait_time -= delay_time

                # cannot wait negative time
                stop_event.wait(max(wait_time, 0))

        except Exception as e:
            traceback.print_exc(e)
        finally:
            player.reset()
            mapper.reset()
            groover.reset()
