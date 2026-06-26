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


import loeric.core.element as le
import loeric.core.inputs as li
import loeric.core.outputs as lo
import loeric.core.paths as lp


@lp.expose("_input_interfaces", "input")
@lp.expose("_output_interfaces", "output")
class Player:

    _input_interfaces: dict[li.InputInterface]
    _output_interfaces: dict[lo.OutputInterface]

    def __init__(self, config):

        self._input_interfaces = {}
        for i in config["input"]:
            interface = li.InputInterface.create_input(config["input"][i], name=i)
            if interface is not None:
                self._input_interfaces[i] = interface

        self._output_interfaces = {}
        for o in config["output"]:
            interface = lo.OutputInterface.create_output(config["output"][o], name=o)
            if interface is not None:
                self._output_interfaces[o] = interface

        self._tempo = le.Tempo(qpm=120)
        self._message_queue = le.LOERICQueue()

    def _update(self, events: list[le.LOERICElement], tick):

        # update own tempo
        for e in events:
            if not e.is_performable:
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

        for o in self._output_interfaces:
            self._output_interfaces[o].play_events(events, tick)

    def reset(self):
        """Close all interfaces."""
        for i in self._input_interfaces:
            self._input_interfaces[i].reset()
        for o in self._output_interfaces:
            self._output_interfaces[o].reset()

    def _get(self):
        val = {}
        for i in self._input_interfaces:
            val |= self._input_interfaces[i].get()
        return val

    def _set(self, contour_values: dict):
        for o in self._output_interfaces:
            self._output_interfaces[o].set(contour_values)

    def step(self, mapper, contour_manager, groover, tune, tick, null_events=False):

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
        groover.update(performance_tick, window, null_events=null_events)

        # set control outputs for the player
        self._set(contour_values)

        # get performed things
        groover_out = groover.pop(tick)

        # update internal
        self._update(groover_out, tick)

        # play them
        self._play_events(groover_out, tick)

        # check if groover output end of score
        finished = False
        for s in groover_out:
            finished = finished or isinstance(s, le.EndOfScore)

        if finished:
            for o in self._output_interfaces:
                finished = finished and self._output_interfaces[o].done()

        return finished

    @property
    def eighth_duration_seconds(self) -> float:
        return 30 / self._tempo.qpm
