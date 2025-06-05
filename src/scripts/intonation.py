import sounddevice as sd
import time
import math
import argparse
import mido
import aubio
import numpy as np

sample_rate = 44100
win_size = 512
hop_size = 256

block_size = hop_size  # sample_rate // 10

pitch_o = aubio.pitch("yin", win_size, hop_size, sample_rate)
pitch_o.set_unit("midi")
pitch_o.set_silence(-40)

onsets = []
pitches = []

intonation = np.zeros(127)
transpose_octaves = 0
counts = np.zeros(127)
old_index = 0
port = None

intonation_responsiveness = 1
loudness_responsiveness = 1
loudness_control = 11
loudness_invert = False

old_cc_value = None
level = 0
min_level = 100000000
max_level = -100000000


def pitch_analysis(samples, responsiveness=0.75):
    global old_index, last_midi
    # for i in range(block_size // hop_size):
    # midi = pitch_o(samples[i * hop_size : (i + 1) * hop_size])[0]
    midi = pitch_o(samples)[0]
    confidence = pitch_o.get_confidence()

    if confidence > 0.9 and midi != 0:

        # midi = 69 + 12 * math.log2(pitch / 440.0)
        midi += transpose_octaves * 12
        if midi > 127:
            return

        old_intonation = intonation.copy()

        index = round(midi)
        value = midi - round(midi)

        counts[index] += 1
        if counts[index] == 1:
            intonation[index] = value
        else:
            N = counts[index]
            intonation[index] *= 1 - responsiveness
            intonation[index] += value * responsiveness

        if abs(intonation[index] - old_intonation[index]) >= 0.05:
            port.send(mido.Message("note_off", note=old_index, time=0, velocity=0))
            value = int(intonation[index] * 4096)
            port.send(mido.Message("pitchwheel", pitch=value))
            port.send(mido.Message("note_on", note=index, time=0, velocity=64))

            old_index = index
            # print(index, intonation[index])

        # print()


def loudness_analysis(samples, responsiveness=1, control=11, invert=False):
    global level, min_level, max_level, old_cc_value
    old_level = level
    level = np.sqrt(np.mean(samples**2))

    level = responsiveness * level + (1 - responsiveness) * level

    min_l = min(min_level, level)
    min_level *= 1 - responsiveness
    min_level += responsiveness * min_l

    max_l = max(max_level, level)
    max_level *= 1 - responsiveness
    max_level += responsiveness * max_l

    diff = max_level - min_level
    if diff == 0:
        value = 0
    else:
        value = (level - min_level) / (max_level - min_level)
    value = max(value, 0)
    value = min(value, 1)

    if invert:
        value = 1 - value

    cc_value = int(value * 127)
    cc_value = max(0, cc_value)
    cc_value = min(127, cc_value)

    if cc_value != old_cc_value:
        old_cc_value = cc_value

        msg = mido.Message(
            "control_change",
            channel=0,
            control=control,
            value=cc_value,
        )

        # send the message
        port.send(msg)
        # print(f"{round(value,2)}\t{msg.value}")


def callback(indata, frames, ctime, status):
    global port, old_index, intonation, transpose_octaves, loudness_responsiveness, loudness_control, loudness_invert, intonation_responsiveness

    samples = np.float32(np.mean(indata, axis=1))

    if intonation_responsiveness != 0:
        pitch_analysis(samples, responsiveness=intonation_responsiveness)
    if loudness_responsiveness != 0:
        loudness_analysis(
            samples,
            responsiveness=loudness_responsiveness,
            control=loudness_control,
            invert=loudness_invert,
        )


def main():
    global port, transpose_octaves, loudness_responsiveness, loudness_control, loudness_invert, intonation_responsiveness
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", help="the output MIDI port.", type=int)
    parser.add_argument(
        "-lr",
        "--loudness-responsiveness",
        help="the responsiveness for loudness.",
        type=float,
    )
    parser.add_argument(
        "-ir",
        "--intonation-responsiveness",
        help="the responsiveness for intonation.",
        type=float,
    )
    parser.add_argument(
        "-t",
        "--transpose_octaves",
        help="the number of octave shift of the signal",
        type=int,
    )
    parser.add_argument(
        "--invert", action="store_true", help="whether to invert the signal or not"
    )
    parser.add_argument(
        "-c",
        "--control",
        help="the control channel on which intensity is sent.",
        default=10,
        type=int,
    )

    args = parser.parse_args()

    if args.output is None:
        human_id = int(time.time())
        port = mido.open_output(f"HUMAN out #{human_id}#", virtual=True)
    else:
        port = mido.open_output(mido.get_output_names()[args.output])

    transpose_octaves = args.transpose_octaves
    intonation_responsiveness = args.intonation_responsiveness
    loudness_responsiveness = args.loudness_responsiveness
    loudness_control = args.control
    loudness_invert = args.invert

    with sd.InputStream(
        callback=callback, channels=1, samplerate=sample_rate, blocksize=block_size
    ):
        print("Listening...")
        input()  # press enter to stop

    port.close()
    import matplotlib.pyplot as plt

    plt.scatter(onsets, pitches)
    plt.show()


main()
