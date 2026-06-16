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
import os

import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)


_MIDI_TO_FREQ_FACTOR = 440.0 * (2.0 ** (-69.0 / 12.0))


def plot_contours(manager, tune, plot_keys):
    """Plot the specified contours."""
    x = tune.float_times
    pitches = tune.pitches
    x /= max(x)
    plot_num = len(plot_keys)
    fig = plt.figure(figsize=(20, 5 * plot_num))
    axs = fig.subplots(plot_num, 1, sharex=True)
    if plot_num == 1:
        axs = [axs]
    for ax, contour in zip(axs, plot_keys):
        ax.step(
            x,
            (pitches - min(pitches)) / (max(pitches) - min(pitches)),
            linestyle=":",
            where="post",
        )
        ax.step(x, manager.contours[contour].values, where="post", marker="x")
        ax.set_xlim(min(x) - 0.01, 1 + 0.01)
    plt.tight_layout()
    plt.show()


def pin_to_cores(cores):
    """Pin LOERIC to a certain number of cores (assigned sequentially starting from core 0)."""
    try:
        os.sched_setaffinity(0, set(cores))
        logger.info(f"Main loop pinned to CPU cores {list(cores)}.")
    except Exception as e:
        logger.debug(f"Could not pin to cores: {e}")


def set_realtime_priority():
    """Attempt to raise the process to SCHED_FIFO priority (Linux, needs cap_sys_nice)."""
    try:
        import ctypes

        SCHED_FIFO = 1

        class SchedParam(ctypes.Structure):
            _fields_ = [("sched_priority", ctypes.c_int)]

        param = SchedParam(sched_priority=49)  # just below kernel threads (50-99)
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        ret = libc.sched_setscheduler(0, SCHED_FIFO, ctypes.byref(param))
        if ret == 0:
            logger.debug("Real-time scheduling (SCHED_FIFO, pri=49) granted.")
            logger.info("LOERIC running with real-time priority.")
        else:
            logger.debug(
                f"sched_setscheduler returned {ret}; running at default priority."
            )
            logger.info("LOERIC running with normal priority.")
    except Exception as e:
        logger.debug(f"Could not set real-time priority: {e}")


"""
def play(tune, player, mapper, groover, contour_manager, args):
    Play a tune.
    import cProfile
    import io
    import pstats
    from pstats import SortKey

    pr = cProfile.Profile()
    pr.enable()

    start_time = tune.start_time.eighth_duration

    groover.init_key_signature(tune.key_signatures[0])
    groover.init_time_signature(tune.time_signatures[0])

    groover.set_tempo(args["qpm"], start_time)

    # timekeeping
    tick = le.TimeDelta(eighth_duration=start_time - groover.lookahead_size)
    time_division = le.TimeDelta(eighth_duration=1 / le.MINIMUM_QUARTER_DIVISION)

    time_division_f = time_division.eighth_duration

    finish = False

    try:
        while tick < start_time - groover.lookahead_size:
            finish = player.step(
                mapper,
                contour_manager,
                groover,
                tune,
                tick,
            )
            tick += time_division

        input("Press any key to start")

        # start actual loop
        while not finish:
            start_time = time.perf_counter()

            finish = player.step(
                mapper, contour_manager, groover, tune, tick, null_events=True
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

    except KeyboardInterrupt:
        print("Playback terminated.")

    finally:
        player.shutdown()

        pr.disable()
        s = io.StringIO()
        sortby = SortKey.CUMULATIVE
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby).reverse_order()
        # ps.print_stats()
        # print(s.getvalue())
"""


def midi_to_freq(midi):
    """Convert a MIDI not number to its frequency."""
    return _MIDI_TO_FREQ_FACTOR * np.exp2(midi / 12.0)
