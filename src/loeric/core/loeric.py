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
import loeric.core.tune as tu

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

        self._instance = None
        self._running = False

        if self._mode == "process":
            self._command_queue = multiprocessing.Queue()
        else:
            self._command_queue = queue.Queue()

    def set_tune(self, tune: tu.Tune):
        """Assign a tune to LOERIC."""
        self._tune = tune

    @staticmethod
    def infer_tune_type(tune: tu.Tune):
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
        """Set tempo for LOERIC's performance in quarters per minute (QPM).

        Defaults to 120 QPM.
        """
        self._qpm = tempo
        self._command_queue.put(
            LOERICCommand(command="tempo", payload={"tempo": tempo})
        )

    def set_attribute(self, path: str, value: float):
        assert (
            self._running
        ), "'set_attribute' can only be used on a running LOERIC instance. Make sure to call 'start' first."
        self._command_queue.put(
            LOERICCommand(
                command="set",
                payload={"path": lp.LOERICPath(path=path), "value": value},
            )
        )

    def get_attribute(self, path: str, timeout: float = 1.0):
        """Retrieve the value at a config-style path from the running instance.

        The returned value may be a scalar (int, float, str, bool),
        a dict, a list, or an object, depending on what lives at *path*.
        Returns ``None`` if the path could not be resolved or the call times out.

        :param path: slash-separated config path,
            e.g. ``'player/output/headphones/volume'``.
        :param timeout: seconds to wait for the running instance to respond.
        :return: the value at *path*, or ``None``.
        """
        response_queue = (
            multiprocessing.Queue() if self._mode == "process" else queue.Queue()
        )
        self._command_queue.put(
            LOERICCommand(
                command="get",
                payload={
                    "path": lp.LOERICPath(path=path),
                    "response": response_queue,
                },
            )
        )
        try:
            return response_queue.get(timeout=timeout)
        except Exception:
            logger.warning(f"get_attribute timed out for path '{path}'")
            return None

    def start(self, wait_for_prompt=False):
        """Start LOERIC in a new process."""
        # event to stop playback

        if self._mode == "process":
            # event to start playback if wait for prompt
            # event to signal ready state
            ready_event = multiprocessing.Event()
            self._instance = multiprocessing.Process(
                target=LOERIC._run,
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
            self._instance = threading.Thread(
                target=LOERIC._run,
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

        self._instance.start()

        if wait_for_prompt:
            ready_event.wait()
            input("Press any key to start...")

        self._command_queue.put(LOERICCommand(command="start"))

        self._running = True

    def stop(self):
        """Stop the LOERIC process."""
        if self._instance:

            # make sure that the process is not stuck
            # waiting for start
            if not self._running:
                self._command_queue.put(LOERICCommand(command="start"))

            while self._instance.is_alive():
                self._command_queue.put(LOERICCommand(command="stop"))
                self._instance.join()

            self._instance = None

            self._running = False

    def join(self, timeout=None):
        """Wait for the LOERIC process to complete."""
        if self._instance and self._instance.is_alive():
            self._instance.join(timeout)

    @staticmethod
    def _run(
        config: dict,
        tune: tu.Tune,
        qpm: float,
        wait_for_prompt: bool,
        command_queue: queue.Queue | multiprocessing.Queue,
        ready_event: threading.Event | multiprocessing.Event,
        mode: str,
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
        start_time = tune.start_time
        groover.set_tempo(qpm, start_time)

        # timekeeping
        tick = le.TimeDelta(eighth_duration=start_time - groover.lookahead_size)
        time_division = le.TimeDelta(
            eighth_duration=le.ONE_OVER_MINIMUM_QUARTER_DIVISION
        )
        time_division_f = time_division.eighth_duration

        def wait_for_command(command):
            while True:
                cmd = command_queue.get()
                if cmd.command == command:
                    return cmd

        def handle_command(cmd: LOERICCommand):
            logger.info(f"Received command: {cmd}")
            if cmd.command == "stop":
                return True  # signal caller to break
            if cmd.command == "tempo":
                groover.set_tempo(cmd.payload["tempo"], tick)
            elif cmd.command == "set":
                path: lp.LOERICPath = cmd.payload["path"]
                value = cmd.payload["value"]
                root_obj = roots.get(path.top)
                if root_obj is None:
                    logger.warning(f"Unknown root '{path.top}' in path '{path.path}'")
                else:
                    lp.LOERICPath.set(root_obj, path.tail, value)
            elif cmd.command == "get":
                path: lp.LOERICPath = cmd.payload["path"]
                response = cmd.payload["response"]
                root_obj = roots.get(path.top)
                if root_obj is None:
                    logger.warning(f"Unknown root '{path.top}' in path '{path.path}'")
                    response.put(None)
                else:
                    response.put(lp.LOERICPath.get(root_obj, path.tail))

            return False  # keep going

        ########## READY PLAYBACK ###############

        try:
            # run in advance until lookahead is reached
            while tick < start_time:
                finish = LOERIC._step(
                    mapper,
                    contour_manager,
                    groover,
                    player,
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
            warned = False

            while not finish:

                # commands
                cmd = None
                if not command_queue.empty():
                    cmd = command_queue.get_nowait()
                    logger.debug(cmd)
                    if handle_command(cmd):
                        break

                start_time = time.perf_counter()

                # step
                finish = LOERIC._step(
                    mapper,
                    contour_manager,
                    groover,
                    player,
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
                    if True:  # not warned:
                        logger.warning(
                            f"Computation ({np.round(delay_time,4)}s) is taking more than time interval ({np.round(wait_time,4)}s)!"
                        )

                        warned = True
                else:
                    warned = False

                wait_time -= delay_time

                # cannot wait negative time
                time.sleep(max(wait_time, 0))

        except Exception:
            traceback.print_exc()
        finally:

            player.reset()
            mapper.reset()
            groover.reset()

    @staticmethod
    def _step(
        mapper: mp.Mapper,
        contour_manager: cnt.ContourManager,
        groover: gr.Groover,
        player: pl.Player,
        tune: tu.Tune,
        tick: le.TimeDelta,
        null_events: bool = False,
    ):

        # update performance time
        performance_tick = tick + groover.lookahead_size
        le.PerformanceClock.set(performance_tick)

        # obtain user inputs and update the mapper
        user_inputs = player.get()
        mapper.set(user_inputs)

        # obtain contours and update the mapper
        raw_contour_values = contour_manager.at(performance_tick)
        mapper.set(raw_contour_values)

        mapper.update()

        # obtain processed control values
        contour_values = mapper.get()

        # obtain elements to process
        score_elements = tune.at(performance_tick)
        window = tune.window(time=performance_tick, size=groover.window_size)

        # feed everything in the groover
        for c in contour_values:
            groover.push(c)

        for u in user_inputs:
            groover.push(u)

        # feed them through the groover
        for s in score_elements:
            groover.push(s)

        # make the groover compute
        groover.update(performance_tick, window, null_events=null_events)

        # set control outputs for the player
        player.set(contour_values)

        # get performed things
        groover_out = groover.pop(tick)

        # update player
        player.update(groover_out, tick)

        # play them
        player.play_events(groover_out, tick)

        # check if groover output end of score
        finished = False
        for s in groover_out:
            finished = finished or isinstance(s, le.EndOfScore)

        # check if player is done playing
        finished = finished and player.done()

        return finished
