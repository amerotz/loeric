import loeric.loeric_utils as lu
import mido
import time
import argparse
import numpy as np
from scipy.fftpack import fft, dct, idct
import matplotlib.pyplot as plt

filename = "/home/marco/git/loeric-align/AMT/COMP_fiddle_reels_aisling_amt.mid"
midi = mido.MidiFile(filename)

onsets = []
pitches = []
velocities = []
t = 0
for msg in midi:
    t += msg.time
    if lu.is_note_on(msg):
        onsets.append(t)
        pitches.append(msg.note)
        velocities.append(msg.velocity)

times = np.array(onsets)
times -= min(times)

"""
X = times[:-1]
Y = np.diff(times)
"""
X = times
Y = np.array(velocities)
Y = np.diff(Y, prepend=velocities[0])

x = np.arange(0, max(X), 0.05)
y = np.interp(x, X, Y)

# 2. Compute FFT
fft_result = np.fft.rfft(y)
frequencies = np.fft.rfftfreq(len(x), d=(x[1] - x[0]))  # frequency bins

# 3. Get magnitude spectrum and ignore DC (index 0)
magnitude = np.abs(fft_result)
# magnitude[0] = 0  # ignore DC
magnitude /= max(magnitude)
magnitude += 1
magnitude **= 16

plt.plot(60 * frequencies[1:], magnitude[1:])

indexes = np.argsort(magnitude)[-10:]
plt.scatter(60 * frequencies[indexes], magnitude[indexes], color="red")
print(60 * frequencies[indexes])
# plt.xscale("log")
plt.tight_layout()
plt.show()
