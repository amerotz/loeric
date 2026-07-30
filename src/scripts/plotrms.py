#!/usr/bin/env python3

import argparse

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
import soundfile as sf
from matplotlib.animation import FuncAnimation


def adaptive_normalize(
    rms_values,
    responsiveness=0.1,
    recovery=0.1,
):
    """Follow RMS values with smoothing and adaptive min/max.

    responsiveness:
        how quickly level follows RMS.

    recovery:
        how quickly min/max recover toward the current level.
    """
    levels = []
    mins = []
    maxs = []
    values = []

    level = 0.0
    min_level = None
    max_level = None

    alpha = responsiveness

    for rms in rms_values:

        # Smooth RMS level
        level += alpha * (rms - level)

        # Adaptive minimum
        if min_level is None or level < min_level:
            min_level = level
        else:
            min_level += alpha * recovery * (level - min_level)

        # Adaptive maximum
        if max_level is None or level > max_level:
            max_level = level
        else:
            max_level += alpha * recovery * (level - max_level)

        # Normalize
        diff = max_level - min_level

        if diff < 1e-12:
            value = 0.0
        else:
            value = np.clip(
                (level - min_level) / diff,
                0.0,
                1.0,
            )

        levels.append(level)
        mins.append(min_level)
        maxs.append(max_level)
        values.append(value)

    return (
        np.array(levels),
        np.array(mins),
        np.array(maxs),
        np.array(values),
    )


def compute_rms(signal, samplerate, buffer_seconds):
    """Compute RMS values over fixed time windows."""
    buffer_size = int(samplerate * buffer_seconds)

    rms_values = []
    times = []

    for start in range(0, len(signal), buffer_size):
        chunk = signal[start : start + buffer_size]

        if len(chunk) == 0:
            continue

        rms = np.sqrt(np.mean(np.square(chunk), dtype=np.float64))

        # Convert to dBFS
        # rms = 20 * np.log10(max(rms, 1e-12))

        rms_values.append(rms)
        times.append(start / samplerate)

    return np.array(times), np.array(rms_values)


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "file",
        help="audio file",
    )

    parser.add_argument(
        "--buffer",
        type=float,
        default=0.1,
        help="RMS window size in seconds",
    )

    parser.add_argument(
        "--responsiveness",
        type=float,
        default=0.1,
        help="RMS smoothing factor",
    )

    parser.add_argument(
        "--recovery",
        type=float,
        default=0.1,
        help="min/max recovery speed",
    )

    args = parser.parse_args()

    # Load audio
    audio, sr = sf.read(args.file)

    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    audio = np.asarray(audio, dtype=np.float32)

    print(f"Sample rate: {sr}")
    print(f"Duration: {len(audio)/sr:.2f}s")

    # RMS analysis
    times, rms = compute_rms(
        audio,
        sr,
        args.buffer,
    )

    level, minimum, maximum, normalized = adaptive_normalize(
        rms,
        responsiveness=args.responsiveness,
        recovery=args.recovery,
    )

    # --------------------------
    # Audio playback
    # --------------------------

    cursor_time = [0.0]
    audio_index = [0]

    def audio_callback(outdata, frames, time_info, status):

        start = audio_index[0]
        end = start + frames

        chunk = audio[start:end]

        if len(chunk) < frames:
            outdata[:, 0] = 0
            outdata[: len(chunk), 0] = chunk
            raise sd.CallbackStop

        outdata[:, 0] = chunk

        audio_index[0] = end
        cursor_time[0] = end / sr

    stream = sd.OutputStream(
        samplerate=sr,
        channels=1,
        dtype="float32",
        callback=audio_callback,
    )

    # --------------------------
    # Plot
    # --------------------------

    fig, axes = plt.subplots(
        3,
        1,
        figsize=(12, 8),
        sharex=True,
    )

    # RMS
    axes[0].plot(
        times,
        rms,
        color="gray",
        label="RMS",
    )

    axes[0].plot(
        times,
        level,
        color="blue",
        label="level",
    )

    axes[0].set_ylabel("Amplitude")
    axes[0].legend()
    axes[0].grid()

    # Min/max
    axes[1].plot(
        times,
        level,
        color="blue",
        label="level",
    )

    axes[1].plot(
        times,
        minimum,
        color="green",
        label="min",
    )

    axes[1].plot(
        times,
        maximum,
        color="red",
        label="max",
    )

    axes[1].set_ylabel("Amplitude")
    axes[1].legend()
    axes[1].grid()

    # Normalized
    axes[2].plot(
        times,
        normalized,
        color="purple",
        label="normalized",
    )

    axes[2].set_ylim(0, 1)
    axes[2].set_xlabel("Time (s)")
    axes[2].set_ylabel("Value")
    axes[2].legend()
    axes[2].grid()

    # Cursor
    cursor_lines = []

    for ax in axes:
        line = ax.axvline(
            0,
            color="black",
            linewidth=2,
        )
        cursor_lines.append(line)

    def update_cursor(_):

        t = cursor_time[0]

        for line in cursor_lines:
            line.set_xdata([t, t])

        return cursor_lines

    animation = FuncAnimation(
        fig,
        update_cursor,
        interval=30,
        blit=True,
    )

    plt.tight_layout()

    # Start playback after plot is ready
    stream.start()

    try:
        plt.show()
    finally:
        stream.stop()
        stream.close()


if __name__ == "__main__":
    main()
