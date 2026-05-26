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
import time

import numpy as np

import loeric.element as le

logger = logging.getLogger(__name__)


def play(tune, player, mapper, groover, contour_manager, args):

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
            start_time = time.time()

            finish = player.step(
                mapper, contour_manager, groover, tune, tick, null_events=True
            )

            tick += time_division

            # fraction of eight note converted to seconds
            wait_time = time_division.eighth_duration * player.eighth_duration_seconds

            # compensate loop duration
            delay_time = time.time() - start_time
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


def midi_to_freq(midi):
    return 440 * 2 ** ((midi - 69) / 12)
