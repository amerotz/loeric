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
import threading

import mido
import numpy as np
import sounddevice as sd
import tinysoundfont

import loeric.core.paths as lp
import loeric.core.player.outputs.midi as lom

logger = logging.getLogger(__name__)


class SynthOutput(mido.ports.BaseOutput):

    def __init__(
        self,
        name: str,
        path: str,
        program: int,
        gain: float,
        device: str,
        volume: float,
        samplerate: int,
        channels: int,
        **kwargs,
    ):
        self._name = name
        self._path = path
        self._program = program
        self._gain = gain
        self._device = device
        self._volume = volume
        self._lock = threading.RLock()
        self._samplerate = samplerate
        self._channels = channels

        self._synth = tinysoundfont.Synth(gain=self._gain, samplerate=self._samplerate)
        self._soundfont_id = self._synth.sfload(self._path)
        self._stream = None
        self._synth_is_running = False

        for channel in range(16):
            self._synth.program_select(channel, self._soundfont_id, 0, self._program)

        CALLBACK_CHANNELS = min(self._channels, 2)

        def callback(outdata, frames, time, status):
            if status:
                logger.warning("Audio callback status: %s", status)
            buf = self._synth.generate(samples=frames)
            buf = np.frombuffer(buf, dtype=np.float32).reshape(-1, 2)

            # mono
            if CALLBACK_CHANNELS == 1:
                buf = buf.mean(axis=1).reshape(-1, 1)

            # change volume by scaling signal
            buf *= self._volume

            outdata[:, :CALLBACK_CHANNELS] = buf

        self._stream = sd.OutputStream(
            samplerate=self._synth.samplerate,
            blocksize=0,
            device=self._device,
            channels=self._channels,
            latency="high",
            dtype="float32",
            callback=callback,
        )
        self._stream.start()
        self._synth_is_running = True

        mido.ports.BaseOutput.__init__(self, name=self._name, **kwargs)

    def _send(self, msg):
        with self._lock:
            if msg.type == "note_on":
                if msg.velocity == 0:
                    self._synth.noteoff(msg.channel, msg.note)
                else:
                    self._synth.noteon(msg.channel, msg.note, msg.velocity)
            elif msg.type == "note_off":
                self._synth.noteoff(msg.channel, msg.note)
            elif msg.type == "pitchwheel":
                self._synth.pitchbend(msg.channel, msg.pitch + 8192)
            elif msg.type == "control_change":
                self._synth.control_change(msg.channel, msg.control, msg.value)
            else:
                logger.warning("Unknown MIDI message type: %s", msg.type)

    def close(self):
        if self._synth_is_running:
            with self._lock:
                self._synth.sounds_off()
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            if self._soundfont_id is not None:
                self._synth.sfunload(self._soundfont_id)
            self._synth_is_running = False

        super().close()

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = value


class SoundfontOutputConfig(lom.MIDIOutputConfig):
    path: str
    program: int
    gain: float
    device: str
    volume: float
    samplerate: int
    channels: int
    port: None = None


@lp.readonly("program")
@lp.readonly("channels")
@lp.readonly("path")
@lp.readonly("gain")
@lp.readonly("samplerate")
@lp.readonly("device")
@lp.expose("_volume", "volume")
class SoundfontOutput(lom.MIDIOutput):

    config_class = SoundfontOutputConfig

    def __init__(
        self,
        path: str,
        program: int,
        gain: float,
        device: str,
        volume: float,
        send_cc: bool,
        send_messages: bool,
        velocity_range: list[int],
        pitchbend_range: int,
        controls: dict[str, int],
        samplerate: int,
        channels: int,
        port=None,
        **kwargs,
    ):

        assert os.path.isfile(path), f"'{path}' is not a valid path."

        self._path = path
        self._program = program
        self._gain = gain
        self._soundfont_id = None
        self._device = device
        self._volume = volume
        self._samplerate = samplerate
        self._channels = channels

        super().__init__(
            port=port,
            controls=controls,
            send_cc=send_cc,
            send_messages=send_messages,
            velocity_range=velocity_range,
            pitchbend_range=pitchbend_range,
            **kwargs,
        )

        # unused
        del self._port

    def _create_output(self):
        """Load the soundfont."""
        return SynthOutput(
            name="LOERIC Synth",
            path=self._path,
            program=self._program,
            gain=self._gain,
            device=self._device,
            volume=self._volume,
            samplerate=self._samplerate,
            channels=self._channels,
        )

    def _set_volume(self, value: float):
        """Override the class' volume setter.

        Propagates changes to the underlying synth.
        """
        if not self._active:
            return
        value = lp.coerce(float, value)

        self._out.volume = value
        self._volume = value
