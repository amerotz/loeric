import argparse
import time

import aubio
import mido
import numpy as np
import sounddevice as sd


hop_size = None
onsets = []
pitches = []

intonation = np.zeros(127)
transpose_octaves = 0
old_index = 0
port = None

intonation_responsiveness = 1
loudness_responsiveness = 1
loudness_control = 11
loudness_invert = False
pitch_confidence = 0.9
messages_per_second = 4

old_cc_value = None
level = 0
min_level = 100000000
min_db_level = 100000000
max_level = -100000000


def pitch_analysis(samples, responsiveness=0.75):

    # analyze
    midi = pitch_o(samples)[0]
    confidence = pitch_o.get_confidence()

    # if we have a pitch
    if confidence > pitch_confidence and midi != 0:

        # transpose
        midi += transpose_octaves * 12
        # if midi is out of range, ignore
        if midi > 127 or midi < 0:
            return

        # check intonation
        old_intonation = intonation.copy()

        # check what note and how much deviation
        index = round(midi)
        value = midi - round(midi)

        # update intonation of note
        intonation[index] *= 1 - responsiveness
        intonation[index] += value * responsiveness

        # if intonation changed of at least 5 cents
        if abs(intonation[index] - old_intonation[index]) >= 0.05:

            return index

    return None


def loudness_analysis(samples, responsiveness=1, control=11, invert=False):
    global level, min_level, max_level, old_cc_value, min_db_level

    # calculate current rms and db
    level = np.sqrt(np.mean(samples**2))
    db_level = 20 * np.log10(np.abs(samples).mean())

    # rolling avg of current level
    level = responsiveness * level + (1 - responsiveness) * level

    # find new minimum
    min_l = min(min_level, level)
    min_level *= 1 - responsiveness
    min_level += responsiveness * min_l

    # set new silence for pitch detection
    old_db_min = min_db_level
    min_db_level = min(min_db_level, db_level)

    # only change if different
    if old_db_min != min_db_level:
        pitch_o.set_silence(min_db_level)

    # find new max level
    max_l = max(max_level, level)
    max_level *= 1 - responsiveness
    max_level += responsiveness * max_l

    # convert to MIDI cc
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

    # if value is new, send it
    if cc_value != old_cc_value:

        old_cc_value = cc_value

        return cc_value
    else:
        return None


loudness_analysis.last_sent = 0


buffer = []


def callback(indata, frames, ctime, status):
    global buffer

    buffer.append(np.float32(np.mean(indata, axis=1)))
    if len(buffer) == messages_per_second:
        buffer = buffer[1:]

    samples = np.concatenate(buffer)

    cc_value = None
    int_note = None

    # check intonation
    if intonation_responsiveness != 0:
        int_note = pitch_analysis(
            samples[-hop_size:], responsiveness=intonation_responsiveness
        )
        if int_note is not None and int_note not in callback.intonation_queue:
            callback.intonation_queue.append(int_note)

    # check loudness
    if loudness_responsiveness != 0:
        cc_value = loudness_analysis(
            samples,
            responsiveness=loudness_responsiveness,
            control=loudness_control,
            invert=loudness_invert,
        )

    # can we send the message?
    current_time = time.time()
    if current_time - callback.last_sent >= 1 / messages_per_second:

        # reset timer
        callback.last_sent = current_time

        # loudness
        if cc_value is not None:
            msg = mido.Message(
                "control_change",
                channel=0,
                control=loudness_control,
                value=cc_value,
            )

            # send the message
            port.send(msg)
            print(f"INSTY:\t{loudness_control}\t{cc_value}")

        # intonation
        if len(callback.intonation_queue) != 0:
            note = callback.intonation_queue.pop(0)
            if note is not None:

                # calculate value to send in pitchbend
                value = int(intonation[note] * 4096)

                # send message
                port.send(mido.Message("pitchwheel", pitch=value))
                port.send(mido.Message("note_on", note=note, time=0, velocity=64))
                print(f"PITCH:\t{note}\t{value}")


callback.last_sent = 0
callback.intonation_queue = []


def main():
    global port, transpose_octaves, loudness_responsiveness, loudness_control, loudness_invert, intonation_responsiveness, pitch_o, pitch_confidence, messages_per_second, hop_size
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
        "--transpose-octaves",
        help="the number of octave shift of the signal",
        type=int,
        default=0,
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
    parser.add_argument(
        "-k",
        "--pitch-confidence",
        help="the minimum pitch confidence to detect intonation.",
        default=0.9,
        type=float,
    )
    parser.add_argument(
        "-m",
        "--messages-per-second",
        help="the maximum amount of messages to send in one second.",
        default=4,
        type=int,
    )
    parser.add_argument(
        "-d",
        "--device-index",
        help="the index of the audio device",
        default=None,
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
    messages_per_second = args.messages_per_second

    sample_rate = 44100
    win_size = sample_rate // messages_per_second
    hop_size = 512

    block_size = hop_size

    pitch_o = aubio.pitch(
        method="yin", buf_size=win_size, hop_size=hop_size, samplerate=sample_rate
    )
    pitch_o.set_unit("midi")
    pitch_o.set_silence(-70)

    pitch_confidence = args.pitch_confidence

    if args.device_index is None:
        print(
            "No audio device selected. Invoke again adding '--device-index INDEX using the devices below."
        )
        print(sd.query_devices())
        exit()

    with sd.InputStream(
        callback=callback, channels=1, samplerate=sample_rate, blocksize=block_size
    ):
        print("Listening...")
        while input() != "exit":
            pass

    port.close()


main()
