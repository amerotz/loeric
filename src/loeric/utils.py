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

    start_time = tune.start_time.eighth_duration

    groover.set_tempo(args["qpm"], start_time)

    # timekeeping
    tick = le.TimeDelta(eighth_duration=start_time - groover.lookahead_size)
    time_division = le.TimeDelta(eighth_duration=2 / le.MINIMUM_QUARTER_DIVISION)

    finish = False

    try:
        while tick < start_time:
            finish = player.step(mapper, contour_manager, groover, tune, tick)
            tick += time_division

        input("Press any key to start")

        # start actual loop
        while not finish:
            start_time = time.time()

            finish = player.step(mapper, contour_manager, groover, tune, tick)

            tick += time_division

            # fraction of eight note converted to seconds
            wait_time = time_division.eighth_duration * player.eighth_duration_seconds

            # compensate loop duration
            delay_time = time.time() - start_time
            wait_time -= delay_time

            # cannot wait negative time
            time.sleep(max(wait_time, 0))

    except KeyboardInterrupt:
        print("Playback terminated.")

    finally:
        player.shutdown()


def midi_to_freq(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def freq_to_midi(freq):
    return 69 + 12 * np.log2(freq / 440)
