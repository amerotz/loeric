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

import mido
import sounddevice as sd

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.analysers as la

logger = logging.getLogger(__name__)


@lp.readonly("active")
@lp.readonly("type")
@lp.expose("_analysers", "analysers")
class InputInterface:
    """Abstract base for all input interfaces.

    Subclasses represent concrete input modalities (MIDI, audio, etc.) and
    expose a uniform :meth:`get` / :meth:`reset` interface to the player.
    """

    _analysers: dict[str, la.Analyser]

    def __init__(self, name: str, analysers: dict):
        """Initialise the input interface.

        :param name: identifier for this interface instance.
        """
        self._name = name
        self._type = "uninitialised"
        self._active = True

        self._analysers = {
            a: la.Analyser.create_function(
                analysers[a],
                samplerate=self._samplerate if hasattr(self, "_samplerate") else None,
            )
            for a in analysers
        }

    @staticmethod
    def create_input(config: dict, name: str = None):
        """Instantiate the appropriate input interface from a config dict.

        :param config: interface configuration.
            Must contain ``active`` and ``type`` keys.
        :param name: identifier passed to the created interface.
        :return: a :class:`MIDIInput` or :class:`AudioInput` instance,
            or ``InputInterface`` (uninitialised) if ``active`` is false.
        :raises ValueError: if ``config["type"]`` is not recognised.
        """
        if not config["active"]:
            interface = InputInterface(name=None, analysers={})
            interface._active = False
            interface._type = config["type"] + "(uninitialised)"
            return interface
        if config["type"] == "midi":
            return MIDIInput(name=name, **config)
        elif config["type"] == "audio":
            return AudioInput(name=name, **config)
        else:
            raise ValueError(f"Unknown input interface type {config['type']}.")

    def _callback(self, x, **args):
        """Update all analysers with the new input."""
        for a in self._analysers:
            self._analysers[a].update(x)

    def reset(self):
        """Reset the interface state."""
        pass

    def get(self) -> list[le.LOERICElement]:
        """Return the merged control events from all active analysers.

        :return: a list of events.
        """
        events = []
        for a in self._analysers:
            events.extend(self._analysers[a].get())
        return events


class UnknownMIDIPortException(Exception):
    """Raised if the corresponding MIDI port cannot be found."""

    def __init__(self, port: str):
        super().__init__(f"Could not find MIDI port '{port}'.")


@lp.readonly("port")
class MIDIInput(InputInterface):
    """Input interface for MIDI control change messages.

    Opens a MIDI port and maps incoming CC messages to named control values
    normalised to [0, 1].
    """

    def __init__(self, name: str, port: str, analysers: dict, **kwargs):
        """Open a MIDI input port and register the CC callback.

        :param name: identifier for this interface instance.
        :param port: name of the MIDI input port to open.
        :param controls: mapping of control names to MIDI CC numbers.
        """
        self._type = "midi"

        try:
            self._midi_in = mido.open_input(port)
        except Exception:
            raise UnknownMIDIPortException(port)
        self._midi_in.callback = self._callback

        super().__init__(name, analysers)

        for a in self._analysers:
            assert isinstance(
                self._analysers[a], la.MIDIAnalyser
            ), f"Invalid analyser '{a}' (not a MIDI analyser)."

    def reset(self):
        """Close the MIDI input port."""
        self._midi_in.close()
        logger.info("Closed midi input.")


# parts of this code taken from goofi-pipe audiostream node
@lp.readonly("samplerate")
@lp.readonly("device")
class AudioInput(InputInterface):
    """Input interface for live audio streams.

    Opens a sounddevice input stream and routes incoming frames to a set of
    :class:`AudioAnalyser` analysers. Exposes their outputs as named
    control values via :meth:`get`.
    """

    def __init__(
        self, name: str, device: str, samplerate: int, analysers: dict, **kwargs
    ):
        """Open an audio input stream and initialise all configured analysers.

        :param name: identifier for this interface instance.
        :param device: sounddevice device name or index.
        :param samplerate: sampling rate in Hz.
        :param analysers: mapping of analyser names to their config dicts.
        """
        self._type = "audio"

        self._samplerate = samplerate
        self._device = device
        self._stream = sd.InputStream(
            callback=self._callback,
            samplerate=samplerate,
            device=device,
            dtype="float32",
            channels=1,
        )

        self._stream.start()

        super().__init__(name, analysers)

        for a in self._analysers:
            assert isinstance(
                self._analysers[a], la.AudioAnalyser
            ), f"Invalid analyser '{a}' (not an audio analyser)."

    def _callback(self, indata, frames, time, status):
        """Sounddevice stream callback. Forwards incoming audio to all analysers.

        :param indata: audio frame array, shape ``(frames, channels)``.
        :param frames: number of frames in ``indata``.
        :param time: sounddevice timing info object.
        :param status: sounddevice stream status flags.
        """
        for a in self._analysers:
            self._analysers[a].update(indata)

    def reset(self):
        """Stop and close the audio input stream."""
        # stop and close the stream
        self._stream.stop()
        self._stream.close()
        logger.info("Stopped and closed audio stream.")

    @staticmethod
    def list_audio_devices():
        """List available audio input devices.

        :return: list of device name strings.
            Returns ``["None"]`` if sounddevice is unavailable.
        """
        if sd is None:
            return ["None"]

        devices = sd.query_devices()
        device_names = []
        for device in devices:
            # check if the device is an input device
            if device["max_input_channels"] > 0:
                device_names.append(device["name"])
        return device_names
