import os
import random
import argparse
import subprocess
from loeric.__main__ import main as loeric

from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("--data-dir")
args = parser.parse_args()

# generic parameters
REPETITIONS = 3
INPUT = 0
OUTPUT = 0

instruments = [
    (3, "src/configs/infinite.json", False),
    (2, "src/configs/infinite.json", True),
    (1, "src/configs/infinite.json", False),
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
    bpm = random.randrange(140, 180)

    loeric_args = defaultdict(str)
    loeric_args["source"] = f"{args.data_dir}/{tune}"
    loeric_args["repeat"] = REPETITIONS
    loeric_args["output"] = OUTPUT
    loeric_args["input"] = 0
    loeric_args["human_impact"] = 0
    loeric_args["midi_channel"] = midi_channel
    loeric_args["bpm"] = bpm
    loeric_args["config"] = config_file
    loeric_args["diatonic"] = diatonic
    loeric_args["seed"] = 0
    loeric_args["transpose"] = 0
    loeric_args["no_prompt"] = True
    loeric_args["save"] = False

    loeric(loeric_args)
