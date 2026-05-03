"""
This file is part of LOERIC.

LOERIC is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

LOERIC is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with LOERIC. If not, see <https://www.gnu.org/licenses/>.
"""
import librosa
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import find_peaks


def compute_loudness_librosa(audio_path, chunk_duration=1.0):
    y, sr = librosa.load(audio_path, sr=None)
    y = librosa.util.normalize(y)
    chunk_size = int(sr * chunk_duration)
    loudness_values = []

    for i in range(0, len(y), chunk_size):
        chunk = y[i : i + chunk_size]
        if len(chunk) == 0:
            continue
        # RMS energy
        rms = np.sqrt(np.mean(chunk**2))
        if rms > 0:
            db = 20 * np.log10(rms)
        else:
            db = -np.inf  # silence
        loudness_values.append(db)

    return loudness_values


file = "/media/marco/EXTERNAL/Datasets/Limerick/Limerick Recordings/Brendan-Jigs-THeJoyOfMyLife+TheKillglassLakes+FartherQuinns.wav"
cd = 0.05
og_loudness = compute_loudness_librosa(file, chunk_duration=cd)
loudness = np.divide(og_loudness[1:], og_loudness[:-1])

# 2. Compute FFT
fft_result = np.fft.rfft(loudness)
frequencies = np.fft.rfftfreq(len(loudness), d=cd)  # frequency bins

# 3. Get magnitude spectrum and ignore DC (index 0)
magnitude = np.abs(fft_result)
magnitude[0] = 0  # ignore DC

# 4. Find dominant frequency
dominant_indexes = np.argsort(magnitude)

peaks, _ = find_peaks(loudness)
print(peaks)

# 5. Plot signal and estimated period grid
plt.figure(figsize=(10, 4))
plt.plot(0.1 * np.arange(len(og_loudness)), og_loudness, label="Original Signal")
plt.plot(0.1 * np.arange(1, len(og_loudness), 1), loudness, label="Ratio")
# plt.step(times, pitches, label="Notes")
plt.title("Signal with Estimated Period Grid (from FFT)")
plt.xlabel("x")
plt.ylabel("Amplitude")
plt.grid(True)

'''
for i in dominant_indexes:
    dominant_frequency = abs(frequencies[i])
    estimated_period = 1 / dominant_frequency

    # Output estimated period
    print(f"Estimated period (from FFT): {estimated_period:.4f}")
    print(f"Frequency: {dominant_frequency:.4f}")
    print(f"BPM: {60/estimated_period:.4f}")
    print(f"Mag: {magnitude[i]}")
    print()
    """
    # Add vertical lines at multiples of the estimated period
    period_positions = np.arange(0, 0.1 * len(loudness), estimated_period)
    for px in period_positions:
        plt.axvline(
            px,
            linestyle="--",
            alpha=0.5,
            label=estimated_period if px == period_positions[0] else "",
        )

    plt.legend()
    plt.show()
    plt.clf()
    """
plt.clf()
plt.plot(frequencies, magnitude)
plt.tight_layout()
plt.show()
'''
