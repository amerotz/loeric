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

# set: change internal state
# get: return internal state
# pop(tick): obtain an event at a specific time
# pop(): obtain next event
# push: add an element to the working queue
# update: process the queue

import numpy as np

import loeric.element as le
import loeric.outputs as lo


class Player:

    def __init__(self):
        self._output_interface = lo.MIDIOutput()
        self._input_interface = lo.MIDIInput()
        self._tempo = le.Tempo(qpm=120)
        self._message_queue = le.LOERICQueue()

    def _update(self, events: list[le.LOERICElement], tick):

        # update own tempo
        for e in events:
            self._message_queue.push(e)

        while not self._message_queue.is_empty():
            e = self._message_queue.peek()

            if e.time > tick:
                break
            else:
                e = self._message_queue.pop()
                if isinstance(e, le.Tempo):
                    self._tempo = e

    def _play_events(self, events: list[le.LOERICElement], tick):

        self._output_interface._play_events(events, tick)

    def __setitem__(self, key: str, value: float):
        """Set the control named ``key`` to ``value``."""

    def __getitem__(self, key: str):
        """Get the value of control named ``key``."""

    def reset(self):
        """Reset all variables"""
        self._output_interface.reset()

    def set(self, values: dict):
        pass

    def get(self, key: str = None):
        pass

    @property
    def eighth_duration_seconds(self) -> float:
        return 30 / self._tempo.qpm

    def _step(self, mapper, contour_manager, groover, tune, tick):

        X = np.arange(0, 1, 0.01)
        contour_values = None
        for x in X:
            user_inputs = {"intensity": x, "autonomy": x}
            mapper.set(user_inputs)

            raw_contour_values = {"velocity": 1}
            mapper.set(raw_contour_values)

            mapper.update()

            if contour_values is None:
                contour_values = mapper.get(as_array=True)
            else:
                contour_values = np.vstack((contour_values, mapper.get(as_array=True)))

        import matplotlib.pyplot as plt

        for i, c in enumerate(mapper.get().keys()):
            plt.plot(X, contour_values[:, i], label=c)
            plt.xlim(0, 1.1)
            plt.ylim(0, 1.1)
            plt.tight_layout()
            plt.legend()
            plt.show()
            plt.cla()

        return True

    def _get(self):
        return {"intensity": 1, "autonomy": 1}

    def _set(self, values):
        pass

    def step(self, mapper, contour_manager, groover, tune, tick):

        performance_tick = tick + groover.lookahead_size

        # obtain user inputs and update the mapper
        user_inputs = self._get()
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
        groover.set(contour_values)
        groover.set(user_inputs)

        # feed them through the groover
        for s in score_elements:
            groover.push(s)

        # make the groover compute
        groover.update(performance_tick, window)

        # set control outputs for the player
        self._set(contour_values)

        # get performed things
        groover_out = groover.pop(tick)

        # update internal
        self._update(groover_out, tick)

        # play them
        self._play_events(groover_out, tick)

        groover_out = score_elements
        # check if groover output end of score
        finished = len(groover_out) != 0
        for s in score_elements:
            finished = (
                finished and isinstance(s, le.EndOfScore) and tick >= tune.end_time
            )

        return finished
