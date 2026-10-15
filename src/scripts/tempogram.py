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

import librosa
import sounddevice as sd

sr = 44100


def callback(indata, frames, time, status):
    print(frames)

    try:
        print(frames)
        hop_length = 256

        oenv = librosa.onset.onset_strength(y=indata, sr=sr, hop_length=hop_length)

        return
        tempogram = librosa.feature.tempogram(
            onset_envelope=oenv, sr=sr, hop_length=hop_length, n_ft=frames / 2
        )

        # Compute global onset autocorrelation
        ac_global = librosa.autocorrelate(oenv, max_size=tempogram.shape[0])
        ac_global = librosa.util.normalize(ac_global)

        # Estimate the global tempo for display purposes
        tempo = librosa.feature.tempo(
            onset_envelope=oenv, sr=sr, hop_length=hop_length
        )[0]
        print(tempo)
    except Exception as e:
        print(e)


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
