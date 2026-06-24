import faulthandler
import logging
import multiprocessing
import queue
import threading
import time
import traceback
from dataclasses import dataclass

import numpy as np

import loeric.core.contour as cnt
import loeric.core.element as le
import loeric.core.groover as gr
import loeric.core.mapper as mp
import loeric.core.paths as lp
import loeric.core.player as pl

faulthandler.enable()
# bad code goes here

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LOERICCommand:

    command: str
    payload: dict | None = None

    def __repr__(self):
        return f"(LOERICCommand cmd={self.command} payload={self.payload})"


class LOERIC:

    def __init__(self, config: dict, mode: str = "process"):
        """Initialise internal variables.

        If `mode` is equal to `process`, LOERIC will use `multiprocessing`
        primitives for events and queues; if `thread`, LOERIC will use
        `threading` primitives.
        """
        assert mode in ["process", "thread"]
        self._mode = mode
        self._config = config
        self._tune = None
        self._tune_type = None

        # for performance
        self._qpm = 120

        self._process = None

        if self._mode == "process":
            self._command_queue = multiprocessing.Queue()
        else:
            self._command_queue = queue.Queue()

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

    def set_tempo(self, tempo: float):
        """Set tempo for LOERIC's performance in quarters per minute (QPM). Defaults to 120 QPM."""
        self._qpm = tempo
        self._command_queue.put(
            LOERICCommand(command="tempo", payload={"tempo": tempo})
        )

    def set_attribute(self, path: str, value: float):
        self._command_queue.put(
            LOERICCommand(
                command="set",
                payload={"path": lp.LOERICPath(path=path), "value": value},
            )
        )

    def start(self, wait_for_prompt=False):
        """Start LOERIC in a new process."""
        # event to stop playback

        if self._mode == "process":
            # event to start playback if wait for prompt
            # event to signal ready state
            ready_event = multiprocessing.Event()
            self._process = multiprocessing.Process(
                target=self._run,
                args=(
                    self._config,
                    self._tune,
                    self._qpm,
                    wait_for_prompt,
                    self._command_queue,
                    ready_event,
                    self._mode,
                ),
            )
        else:
            ready_event = threading.Event()
            self._process = threading.Thread(
                target=self._run,
                args=(
                    self._config,
                    self._tune,
                    self._qpm,
                    wait_for_prompt,
                    self._command_queue,
                    ready_event,
                    self._mode,
                ),
            )

        ready_event.clear()

        self._process.start()

        if wait_for_prompt:
            ready_event.wait()
            input("Press any key to start...")

        self._command_queue.put(LOERICCommand(command="start"))

    def stop(self):
        """Stop the LOERIC process."""
        if self._process is not None:
            while self._process.is_alive():
                self._command_queue.put(LOERICCommand(command="stop"))
                self._process.join()
            self._process = None

    def join(self, timeout=None):
        """Wait for the LOERIC process to complete."""
        if self._process and self._process.is_alive():
            self._process.join(timeout)

    @staticmethod
    def _run(
        config,
        tune,
        qpm,
        wait_for_prompt,
        queue,
        ready_event,
        mode,
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

        roots = {
            "player": player,
            "groover": groover,
            "mapper": mapper,
            "contour_manager": contour_manager,
        }

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

        def wait_for_command(command):
            while True:
                cmd = queue.get()
                if cmd.command == command:
                    return cmd

        def handle_command(cmd: LOERICCommand):
            if cmd.command == "stop":
                logger.info("Stop requested")
                return True  # signal caller to break
            if cmd.command == "tempo":
                logger.info("Tempo change")
                groover.set_tempo(cmd.payload["tempo"], tick.eighth_duration)
            elif cmd.command == "set":
                path: lp.LOERICPath = cmd.payload["path"]
                value = cmd.payload["value"]
                root_obj = roots.get(path.top)
                if root_obj is None:
                    logger.warning(f"Unknown root '{path.top}' in path '{path.path}'")
                else:
                    lp.LOERICPath.set(root_obj, path.tail, value)
            return False  # keep going

        ########## READY PLAYBACK ###############

        try:
            # run in advance until lookahead is reached
            while tick < start_time:
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
                wait_for_command("start")

            ########## PLAY ###############

            # start actual loop
            finish = False
            while not finish:

                # commands
                cmd = None
                if not queue.empty():
                    cmd = queue.get_nowait()
                    logger.debug(cmd)
                    if handle_command(cmd):
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
                time.sleep(max(wait_time, 0))

        except Exception as e:
            traceback.print_exc(e)
        finally:
            player.reset()
            mapper.reset()
            groover.reset()
