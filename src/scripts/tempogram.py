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

import numpy as np
import sounddevice as sd

sr = 44100

prev_mag = None
max_mag = 0
data = None
last_values = []


def callback(indata, frames, time, status):

    global prev_mag, max_mag, data, last_values

    if data is None:
        data = indata
    else:
        data = np.concatenate((data, indata))

    if len(data) < sr:
        return

    data = data[-sr:, :]

    mag = np.abs(np.fft.rfft(data))

    if prev_mag is None:
        prev_mag = mag
        return

    diff = (mag - prev_mag).sum().clip(min=0)
    prev_mag = mag

    last_values.append(diff)
    last_values = last_values[-100:]
    max_v = max(last_values)

    diff /= max_v

    if diff > 0.25:
        print("ONSET!", diff)


stream = sd.InputStream(
    samplerate=sr,
    channels=1,
    callback=callback,
    dtype="float32",
)
stream.start()

try:
    while True:
        pass
except KeyboardInterrupt:
    stream.stop()
    stream.close()
