import logging
import multiprocessing as mp
import random
import sys
from multiprocessing import shared_memory

import numpy as np

import loeric.core.element as le
import loeric.core.paths as lp
import loeric.core.player.outputs.base as lob

logger = logging.getLogger(__name__)

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore, QtWidgets

    PYQT_AVAILABLE = True
except Exception:
    logger.error(
        "Could not find packages PyQt-related packages. The 'VisualOutput' port will not be available."
    )
    PYQT_AVAILABLE = False


class VisualOutputConfig(lob.OutputInterfaceConfig):

    width: int
    height: int
    window_size: int
    fps: int
    controls: list[str]


@lp.readonly("window_size")
@lp.readonly("width")
@lp.readonly("height")
@lp.readonly("fps")
@lp.readonly("controls")
class VisualOutput(lob.OutputInterface):
    """Output interface for real-time graphical display of contour values.

    Renders contour signals as scrolling waveforms in a PyQtGraph window
    running in a separate process. Communicates with the GUI process via
    shared memory.

    Only available when PyQt and PyQtGraph are installed.
    """

    config_class = VisualOutputConfig

    def __init__(
        self,
        width: int,
        height: int,
        window_size: int,
        fps: int,
        controls: list[str],
        **kwargs,
    ):
        """Open a graphical output window in a child process.

        :param width: window width in pixels.
        :param height: window height in pixels.
        :param window_size: number of samples shown in the scrolling plot.
        :param fps: target refresh rate in frames per second.
        :param controls: list of contour names to display.
        """
        super().__init__(**kwargs)

        self._width = width
        self._height = height
        self._fps = fps
        self._controls = controls
        self._time_interval = 1000 // fps
        self._window_size = window_size

        if self._active:
            # create gui process
            self._process = mp.Process(
                target=self._graphic_loop, name="LOERIC visual", daemon=True
            )
            self._process.start()

            # create shared memory
            array = np.ones(len(self._controls), dtype=float)

            self._memory = shared_memory.SharedMemory(
                name="loeric-visual-shared-memory",
                create=True,
                size=sys.getsizeof(array),
            )

            # create shared buffer
            self._array = np.ndarray(
                array.shape, dtype=array.dtype, buffer=self._memory.buf
            )

    def _graphic_loop(self):
        """Entry point for the child GUI process.

        Attaches to shared memory, creates the PyQtGraph window, and runs
        the Qt event loop. Closes shared memory on exit.
        """
        # attach to shared memory
        array = np.ones(len(self._controls), dtype=float)
        self._memory = shared_memory.SharedMemory(
            name="loeric-visual-shared-memory", size=sys.getsizeof(array)
        )
        # create shared buffer
        self._array = np.ndarray(
            array.shape, dtype=array.dtype, buffer=self._memory.buf
        )

        try:
            # create app
            app = QtWidgets.QApplication([])

            win = pg.GraphicsLayoutWidget(show=True, size=(self._width, self._height))
            plot = win.addPlot(title="Real-Time Signal")
            plot.enableAutoRange(y=False)
            plot.setYRange(0, 1)

            self._curves = {
                c: plot.plot(
                    pen=pg.mkPen("#{:06x}".format(random.randint(0, 0xFFFFFF)), width=2)
                )
                for c in self._controls
            }

            self._x = np.arange(self._window_size)
            self._ys = {c: np.zeros(self._window_size) for c in self._controls}

            self._timer = QtCore.QTimer()
            self._timer.timeout.connect(self._update)
            self._timer.start(self._time_interval)  # ~60 FPS

            app.exec()
        except Exception:
            self._memory.close()

    def _update(self):
        """Qt timer callback that shifts the scrolling buffers and redraws all curves."""
        for i, c in enumerate(self._controls):
            self._ys[c][:-1] = self._ys[c][1:]
            self._ys[c][-1] = self._array[i]
            self._curves[c].setData(self._x, self._ys[c])

    def play_events(self, events: list[le.LOERICElement], tick: le.TimeDelta | float):
        """Send events to the output."""
        pass

    def reset(self):
        """Reset output state."""
        if not self._active:
            return
        while self._process.is_alive():
            self._process.terminate()
        self._process.close()
        self._memory.close()
        self._memory.unlink()

    def done(self) -> bool:
        """Return ``True``; the visual output has no pending message queue.

        :return: always ``True``.
        """
        return True

    def set(self, inputs: list[le.LOERICElement]):
        """Write current contour values into shared memory for the GUI process.

        :param inputs: list of events to process
        """
        if not self._active:
            return
        # create dict
        contour_values = {
            i.name: i.value for i in inputs if isinstance(i, le.ContourValue)
        }
        for i, c in enumerate(self._controls):
            if c in contour_values:
                self._array[i] = contour_values[c]
