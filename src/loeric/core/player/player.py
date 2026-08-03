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
import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.inputs as li
import loeric.core.player.outputs as lo


class PlayerConfig(pdt.BaseModel):

    input_interfaces: dict[str, li.InputInterfaceConfig]
    output_interfaces: dict[str, lo.OutputInterfaceConfig]


@lp.expose("_input_interfaces", "input")
@lp.expose("_output_interfaces", "output")
class Player:

    config_class = PlayerConfig

    def __init__(self, config: dict):

        if not isinstance(config, PlayerConfig):
            config = PlayerConfig(
                input_interfaces=config["input"], output_interfaces=config["output"]
            )
        print(config.dict())

        self._input_interfaces = {}
        for i in config.input_interfaces:
            interface = li.create_input(config.input_interfaces[i])
            if interface is not None:
                self._input_interfaces[i] = interface

        self._output_interfaces = {}
        for o in config.output_interfaces:
            interface = lo.create_output(config.output_interfaces[o])
            if interface is not None:
                self._output_interfaces[o] = interface

        self._tempo = le.Tempo(qpm=120)
        self._message_queue = le.LOERICQueue()

    def update(self, events: list[le.LOERICElement], tick: le.TimeDelta):

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

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta):

        for o in self._output_interfaces:
            self._output_interfaces[o].play_events(events, tick)

    def reset(self):
        """Close all interfaces."""
        for i in self._input_interfaces:
            self._input_interfaces[i].reset()
        for o in self._output_interfaces:
            self._output_interfaces[o].reset()

    def get(self) -> list[le.LOERICElement]:
        events = []
        for i in self._input_interfaces:
            events.extend(self._input_interfaces[i].get())
        return events

    def set(self, contour_values: list[le.LOERICElement]):
        for o in self._output_interfaces:
            self._output_interfaces[o].set(contour_values)

    def done(self):
        done = True
        for o in self._output_interfaces:
            done = done and self._output_interfaces[o].done()

        return done

    @property
    def eighth_duration_seconds(self) -> float:
        return 30 / self._tempo.qpm
