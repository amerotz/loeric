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
# durations = np.diff(times)

durations = np.round(
    np.random.normal(
        loc=[1.1, 0.9, 1.2, 0.8, 1.1, 0.9, 2, 1],
        scale=[0.1, 0.1, 0.1, 0.1, 0.005, 0.005, 0.005, 0.005],
        size=(32, 8),
    ),
    2,
).flatten()
print(durations.shape)

results = []
means = []
stds = []
wraps = [2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 32, 36]
for i in wraps:
    if i >= len(durations):
        continue
    l = len(durations)
    tot = i * (1 + l // i)
    # print(i, l, tot, 1 + l // i)

    swing = durations.copy()
    if l % i != 0:
        swing = np.pad(durations, (0, tot - l))

    # print()

    swing = swing.reshape(-1, i)
    mean = np.nanmean(swing, axis=0)
    means.append(mean)

    std = np.std(swing, axis=0)
    stds.append(std)
    std = np.divide(std, mean)
    results.append(np.mean(std))

index = np.argmin(results)
print(wraps[index])
print(means[index])
print(stds[index])

"""
X = times
Y = np.array(velocities)
# Y = np.diff(Y, prepend=velocities[0])

x = np.arange(0, max(X), 0.05)
y = np.interp(x, X, Y)

# 2. Compute FFT
fft_result = np.fft.rfft(y)
frequencies = np.fft.rfftfreq(len(x), d=(x[1] - x[0]))  # frequency bins

# 3. Get magnitude spectrum and ignore DC (index 0)
magnitude = np.abs(fft_result)
# magnitude[0] = 0  # ignore DC
magnitude /= max(magnitude)

plt.plot(60 * frequencies[1:], magnitude[1:])

indexes = np.argsort(magnitude)[-10:]
plt.scatter(60 * frequencies[indexes], magnitude[indexes], color="red")
print(60 * frequencies[indexes])
# plt.xscale("log")
plt.tight_layout()
plt.show()
"""
