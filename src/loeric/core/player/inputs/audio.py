import logging

import sounddevice as sd

import loeric.core.paths as lp
import loeric.core.player.analysers as la
import loeric.core.player.inputs.base as lib

logger = logging.getLogger(__name__)


class AudioInputConfig(lib.InputInterfaceConfig):

    device: str
    samplerate: int


# parts of this code taken from goofi-pipe audiostream node
@lp.readonly("samplerate")
@lp.readonly("device")
class AudioInput(lib.InputInterface):
    """Input interface for live audio streams.

    Opens a sounddevice input stream and routes incoming frames to a set of
    :class:`AudioAnalyser` analysers. Exposes their outputs as named
    control values via :meth:`get`.
    """

    config_class = AudioInputConfig

    def __init__(self, device: str, samplerate: int, **kwargs):
        """Open an audio input stream and initialise all configured analysers.

        :param device: sounddevice device name or index.
        :param samplerate: sampling rate in Hz.
        :param analysers: mapping of analyser names to their config dicts.
        """
        self._samplerate = samplerate
        self._device = device

        if kwargs["active"]:
            self._stream = sd.InputStream(
                callback=self._callback,
                samplerate=samplerate,
                device=device,
                dtype="float32",
                channels=1,
            )

            self._stream.start()

        super().__init__(**kwargs)

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
        if not self._active:
            return
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
