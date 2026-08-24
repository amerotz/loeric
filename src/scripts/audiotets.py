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

#!/usr/bin/env python3

import argparse

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
import soundfile as sf
from matplotlib.animation import FuncAnimation
from scipy.signal import butter, sosfilt

# ============================================================
# Perceptual weighting
# ============================================================


def k_weighting(audio, sr):
    """BS.1770-style K-weighting approximation.

    Stage 1:
        RLB high-pass (~38 Hz)

    Stage 2:
        high frequency emphasis

    This removes inaudible low-frequency energy and
    better approximates perceived loudness than raw energy.
    """
    hp = butter(
        2,
        38 / (sr / 2),
        btype="highpass",
        output="sos",
    )

    audio = sosfilt(
        hp,
        audio,
    )

    shelf = butter(
        2,
        1500 / (sr / 2),
        btype="highpass",
        output="sos",
    )

    audio = audio + 0.25 * sosfilt(
        shelf,
        audio,
    )

    return audio


# ============================================================
# Loudness measurement
# ============================================================


def calculate_loudness(
    audio,
    sr,
    hop_seconds,
    window_seconds=0.4,
):
    """Calculate momentary perceptual loudness.

    window_seconds:
        integration time.
        400 ms is used as a perceptual loudness window.

    hop_seconds:
        update rate.
    """
    audio = k_weighting(
        audio,
        sr,
    )

    window = int(sr * window_seconds)

    hop = int(sr * hop_seconds)

    loudness = []
    times = []

    for start in range(
        0,
        len(audio) - window,
        hop,
    ):

        block = audio[start : start + window]

        energy = np.mean(
            block * block,
            dtype=np.float64,
        )

        # logarithmic perception domain
        db = 10 * np.log10(
            max(
                energy,
                1e-12,
            )
        )

        loudness.append(db)

        times.append(start / sr)

    return (
        np.asarray(times),
        np.asarray(loudness),
    )


# ============================================================
# Adaptive loudness mapping
# ============================================================


def adaptive_loudness(
    loudness,
    responsiveness,
    min_recovery,
    max_recovery,
    min_slack_factor,
    max_slack_factor,
):
    """Convert loudness to a stable 0-1 control.

    Envelope behavior:

    - max follows loud attacks immediately
      but leaves headroom proportional to jump.

    - min follows quiet drops immediately
      but recovers slowly.

    This prevents the control from constantly
    sitting at 0 or 1.
    """
    level = None
    minimum = None
    maximum = None

    levels = []
    mins = []
    maxs = []
    values = []

    for loudness_value in loudness:

        # smooth perceptual loudness
        if level is None:
            level = loudness_value

        else:
            level += responsiveness * (loudness_value - level)

        if minimum is None:

            minimum = level
            maximum = level

        else:

            # --------------------------------
            # Minimum envelope
            # --------------------------------

            if level < minimum:

                jump = minimum - level
                minimum = level - jump * min_slack_factor

            else:

                minimum += min_recovery * (level - minimum)

            # --------------------------------
            # Maximum envelope
            # --------------------------------

            if level > maximum:

                jump = level - maximum

                maximum = level + jump * max_slack_factor

            else:

                maximum += max_recovery * (level - maximum)

        value = np.clip(
            (level - minimum)
            / max(
                maximum - minimum,
                1e-9,
            ),
            0,
            1,
        )

        levels.append(level)
        mins.append(minimum)
        maxs.append(maximum)
        values.append(value)

    return (
        np.asarray(levels),
        np.asarray(mins),
        np.asarray(maxs),
        np.asarray(values),
    )


# ============================================================
# Main
# ============================================================


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "file",
    )

    parser.add_argument(
        "--buffer",
        type=float,
        default=0.1,
        help="update interval seconds",
    )

    parser.add_argument(
        "--responsiveness",
        type=float,
        default=0.15,
        help="loudness smoothing",
    )

    parser.add_argument(
        "--min-recovery",
        type=float,
        default=0.001,
        help="minimum upward recovery",
    )

    parser.add_argument(
        "--max-recovery",
        type=float,
        default=0.002,
        help="maximum downward recovery",
    )

    parser.add_argument(
        "--min-slack-factor",
        type=float,
        default=0.2,
        help="fraction of quiet jump added below minimum",
    )

    parser.add_argument(
        "--max-slack-factor",
        type=float,
        default=0.3,
        help="fraction of loud jump added above maximum",
    )

    args = parser.parse_args()

    # -------------------------------
    # Load
    # -------------------------------

    audio, sr = sf.read(args.file)

    if audio.ndim > 1:
        audio = np.mean(
            audio,
            axis=1,
        )

    audio = audio.astype(np.float32)

    print(f"sample rate: {sr}")

    print(f"duration: {len(audio)/sr:.2f}s")

    # -------------------------------
    # Analyse
    # -------------------------------

    times, loudness = calculate_loudness(
        audio,
        sr,
        args.buffer,
        window_seconds=args.buffer,
    )

    level, minimum, maximum, control = adaptive_loudness(
        loudness,
        args.responsiveness,
        args.min_recovery,
        args.max_recovery,
        args.min_slack_factor,
        args.max_slack_factor,
    )

    # -------------------------------
    # Playback
    # -------------------------------

    position = [0]
    cursor = [0]

    def callback(
        outdata,
        frames,
        time,
        status,
    ):

        start = position[0]
        end = start + frames

        outdata[:] = 0

        chunk = audio[start:end]

        outdata[: len(chunk), 0] = chunk

        position[0] = end
        cursor[0] = end / sr

    stream = sd.OutputStream(
        samplerate=sr,
        channels=1,
        callback=callback,
    )

    # -------------------------------
    # Plot
    # -------------------------------

    fig, axes = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
    )

    axes[0].step(
        times,
        loudness,
        color="gray",
        alpha=0.4,
        label="weighted loudness",
    )

    axes[0].step(
        times,
        level,
        color="blue",
        label="level",
    )

    axes[0].step(
        times,
        minimum,
        color="green",
        label="minimum",
    )

    axes[0].step(
        times,
        maximum,
        color="red",
        label="maximum",
    )

    axes[0].legend()
    axes[0].grid()

    axes[1].step(
        times,
        control,
        color="purple",
        label="control",
    )

    axes[1].set_ylim(
        0,
        1,
    )

    axes[1].legend()
    axes[1].grid()
    plt.tight_layout()

    cursors = [
        ax.axvline(
            0,
            color="black",
        )
        for ax in axes
    ]

    def animate(_):

        for c in cursors:

            c.set_xdata(
                [
                    cursor[0],
                    cursor[0],
                ]
            )

        return cursors

    animation = FuncAnimation(
        fig,
        animate,
        interval=30,
        blit=True,
        cache_frame_data=False,
    )

    stream.start()

    try:
        plt.show()

    except KeyboardInterrupt:
        pass

    finally:
        stream.stop()
        stream.close()
        plt.close(fig)


if __name__ == "__main__":
    main()
