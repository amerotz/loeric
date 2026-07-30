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

import pydantic as pdt

import loeric.core.element as le
import loeric.core.module as lm
import loeric.core.paths as lp

logger = logging.getLogger(__name__)


class GrooverConfig(pdt.BaseModel):
    """Configuration that maps pipeline stage names → Config model instances."""

    model_config = {"arbitrary_types_allowed": True}
    modules: dict[str, lm.base.ModuleConfig]

    @pdt.field_validator("modules", mode="before")
    @classmethod
    def validate_modules(cls, v: dict) -> dict:
        validated = {}
        for name, raw in v.items():
            base_name = name.split("#")[0]
            module_cls = lm.LOERICModule.class_registry().get(base_name)
            if module_cls is None:
                raise ValueError(f"Unknown module '{base_name}'")
            validated[name] = module_cls.config_class.model_validate(raw)
        return validated


@lp.expose("_modules", "modules")
class Groover:
    """The core of LOERIC's performance rules."""

    def __init__(self, config: dict | GrooverConfig) -> None:
        """Initialise a groover instance."""
        self._queue = le.LOERICQueue()
        self._working_queue = le.LOERICQueue()

        if not isinstance(config, GrooverConfig):
            config = GrooverConfig(modules=config)

        self._modules = {}
        logger.info("Loading following modules:")
        for name, module_config in config.modules.items():
            logger.info(name)
            self._modules[name] = lm.LOERICModule.create_module(
                name, **module_config.model_dump()
            )

    def push(self, event):
        """Add an element to the groover's working queue.

        Elements are processed by calling ``update(time)``.
        """
        self._working_queue.push(event)

    def set_tempo(self, qpm: float, time: float):
        """Request a specific tempo change at a specific time."""
        self.push(le.UserTempo(qpm=qpm, time=time))

    def init_key_signature(self, key: le.KeySignature):
        """Initialise modules with a key signature."""
        for m in self._modules:
            self._modules[m].set_key_signature(key)

    def init_time_signature(self, meter: le.TimeSignature):
        """Initialise modules with a time signature."""
        for m in self._modules:
            self._modules[m].set_time_signature(meter)

    @property
    def lookahead_size(self):
        size = 1
        for m in self._modules:
            size = max(self._modules[m].lookahead_size, size)
        return size

    @property
    def window_size(self):
        size = 0
        for m in self._modules:
            if self._modules[m].window_size is not None:
                size = max(self._modules[m].window_size, size)
        return size

    def update(
        self,
        time: le.TimeDelta,
        window: list[le.LOERICElement] = None,
        null_events: bool = False,
    ) -> None:
        """Update the groover by going through the working queue and applying the modules.

        Only events at the requested time will be brought to completion, while the others
        will once the new performance time has been reached (and the groover has been updated
        with the latest values).

        :param time: the requested performance time.
        :param window: an optional window of elements forward in time.
        :param null_events: whether or not to update the groover with null events if queue is empty.
        """
        while self._update_step(time, window, null_events):
            pass

    def _update_step(
        self,
        time: le.TimeDelta,
        window: list[le.LOERICElement] = None,
        null_events: bool = False,
    ) -> None:

        wq = self._working_queue

        # get element
        can_process = not wq.is_empty() and wq.peek().time <= time
        if can_process:
            event = wq.pop()
        elif null_events:
            event = le.NullEvent(time=time)
        else:
            return can_process

        modules = self._modules
        out_queue = self._queue

        # run it through the modules
        to_be_processed_by_module = [event]
        for i, m in enumerate(modules):
            module = modules[m]
            spawned_elements = []
            for e in to_be_processed_by_module:
                module_output = module(e, window=window)

                for out in module_output:
                    # module output is at same time
                    # can be processed by next module
                    if out.time <= time:
                        spawned_elements.append(out)
                    # module output is later
                    # should be added to queue for later
                    else:
                        if not isinstance(out, le.NullEvent):
                            wq.push(out)

            # next step will process eveything spawned
            # at current time
            to_be_processed_by_module = spawned_elements

        # after all modules have executed, to_be_processed_by_module
        # contains everything that should go in the final queue
        for el in to_be_processed_by_module:
            if not isinstance(el, le.NullEvent):
                out_queue.push(el)

        return can_process

    def pop(self, time: float = None) -> list:
        """Obtain the next elements to be performed at a specific time.

        :param time: the requested performance time.

        :return: the events at time. If time is None, it returns the
        next event in the queue.
        """
        # return next event
        if time is None:
            return [self._queue.pop()]

        # return all events at time
        events = []
        while not self._queue.is_empty():
            # peek first event
            event = self._queue.peek()
            # if time is in the future, then we are done
            # because the queue is a priority queue
            if event.time > time:
                break
            # otherwise remove it and add it to
            # the events to return
            else:
                events.append(self._queue.pop())
        return events

    def reset(self):
        """Reset all variables."""
        self._queue = le.LOERICQueue()
        self._working_queue = le.LOERICQueue()

        for m in self._modules:
            self._modules[m].reset()
