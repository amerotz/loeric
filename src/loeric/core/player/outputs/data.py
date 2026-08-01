import logging
import threading
import time

import pandas as pd
import pydantic as pdt

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.outputs.base as lob

logger = logging.getLogger(__name__)


class DataOutputConfig(lob.OutputInterfaceConfig):

    path: str
    format: str
    controls: list[str]

    @pdt.field_validator("format")
    @classmethod
    def valid_format(cls, v: str):
        formats: list[str] = [
            "pickle",
            "csv",
            "excel",
            "json",
            "html",
            "xml",
            "latex",
            "feather",
            "parquet",
            "iceberg",
            "orc",
            "sql",
            "stata",
        ]
        if v not in formats:
            raise ValueError(f"Unsupported format {v}.")

        return v


@lp.expose("_path", "path")
@lp.expose("_format", "format", validator=lambda x: x in DataOutput.formats)
@lp.expose("_controls", "controls")
class DataOutput(lob.OutputInterface):
    """Output interface that records contour values to a file.

    Samples contour values at a fixed rate in a background thread and writes
    the accumulated data to disk in the chosen format when :meth:`done` is called.

    Supported formats are listed in :attr:`formats`.
    """

    config_class = DataOutputConfig

    def __init__(self, format: str, path: str, controls: list[str]):
        """Initialise the data output and start the background recording thread.

        :param file_format: output file format; must be a value in :attr:`formats`.
        :param path: destination file path.
        :param controls: list of contour names to record.
        :raises AssertionError: if *file_format* is not in :attr:`formats`.
        """
        super().__init__()

        self._type = "data"
        self._format = format
        self._path = path
        self._controls = controls
        self._append_index = 0
        self._thread = threading.Thread(target=self._data_thread)
        self._done = threading.Event()
        self._done_saving = threading.Event()
        self._message_interval = 1 / 10

        self._df = pd.DataFrame(columns=["contour", "time", "value"])

        self._thread.start()

    def _data_thread(self):
        """Add contour values to database every fixed interval.

        Serialise the internal DataFrame to the configured format
        and path when the player asks to be done.
        """
        idx = 0
        df = self._df
        controls = self._controls
        contour_values = self._contour_values

        while not self._done.is_set():

            # current time
            t = time.time()

            # add all relevant contours
            for c in contour_values:
                if c in controls:
                    df.loc[idx] = [c, t, contour_values[c]]
                    idx += 1

            self._done.wait(self._message_interval)

        # save
        getattr(self._df, f"to_{self._format}")(self._path, index=False)

        logger.info(f"Saved to {self._path}.")
        self._done_saving.set()

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Send events to the output."""
        pass

    def reset(self):
        """Reset output state."""
        while self._thread.is_alive():
            self._done.set()

        self._done.clear()
        self._append_index = 0
        self._df = pd.DataFrame(columns=["contour", "time", "value"])
        self._done.clear()

    def done(self) -> bool:
        """Stop the recording thread and check if it is done saving.

        :return: whether the thread has saved the file
        """
        self._done.set()

        return self._done_saving.is_set()
