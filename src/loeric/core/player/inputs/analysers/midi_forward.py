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

import threading
import time
from typing import Literal

import loeric.core.context as lctx
import loeric.core.element as le
from loeric.core.player.inputs.analysers.midi import MIDIAnalyser, MIDIAnalyserConfig


class MIDINoteForwarderConfig(MIDIAnalyserConfig):
    """Config for :class:`MIDINoteForwarder`. No additional fields."""

    type: Literal["midi_forward"]


class MIDINoteForwarder(MIDIAnalyser):
    """MIDI analyser that forwards the played notes down the pipeline.

    Every note-on becomes a :class:`~loeric.core.element.UserNote`, which
    goes through the modules like any other element. It is meant for modules
    that need to know what the performer plays, such as
    :class:`~loeric.core.modules.score_tracker.ScoreTrackerModule`.
    """

    config_class = MIDINoteForwarderConfig

    def __init__(self, **kwargs):
        """Initialise the forwarder.

        :param kwargs: forwarded to :class:`MIDIAnalyser`.
        """
        super().__init__(**kwargs)

        # played notes as (wall-clock time, pitch), shared by the MIDI
        # callback thread and the performance thread
        self._notes = []
        self._lock = threading.Lock()

    def update(self, message):
        """Remember a note-on with the time it was played.

        Runs on the MIDI callback thread, so it does the bare minimum.

        :param message: incoming MIDI message.
        """
        if not self._active:
            return

        if message.type != "note_on" or message.velocity == 0:
            return

        with self._lock:
            self._notes.append((time.perf_counter(), message.note))

    def get(self) -> list[le.LOERICElement]:
        """Return and clear the notes played since the last call.

        :return: list of :class:`~loeric.core.element.UserNote`.
        """
        with self._lock:
            notes, self._notes = self._notes, []

        # the notes are due at the current performance time
        now = lctx.PerformanceClock.now()

        return [le.UserNote(pitch=p, wall_time=t, time=now) for t, p in notes]

    def reset(self):
        """Forget the notes not returned yet."""
        with self._lock:
            self._notes = []
