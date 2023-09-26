import os
import random
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir")
args = parser.parse_args()

# generic parameters
REPETITIONS = 1
INPUT = 0
OUTPUT = 0

instruments = [
    (3, "configs/flute.json", False),
    (2, "configs/infinite.json", True),
    (1, "configs/flute.json", False),
]

tune_list = os.listdir(args.data_dir)
# play tunes in directory
while True:
    index = random.randrange(len(tune_list))
    tune = tune_list[index]
    tune_list.remove(tune)

    index = random.randrange(3)
    midi_channel, config_file, diatonic = instruments[index]

    # play this tune
    bpm = random.randrange(130, 160)
    command = f"python3 loeric {args.data_dir}/{tune} -r {REPETITIONS} -i {INPUT} -o {OUTPUT} -mc {midi_channel} -bpm {bpm}  --no-prompt --config {config_file}"
    if diatonic:
        command += " -d"

    print(command)
    ret_value = os.system(command)

    ret_value = os.waitstatus_to_exitcode(ret_value)
    if os.WIFSIGNALED(ret_value):
        exit()
