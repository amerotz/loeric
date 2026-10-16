import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument(
    "file",
    type=str,
)
args = vars(parser.parse_args())

# load config
with open(args["file"], "r") as f:
    config = json.load(f)


def bfs(config, level=0):

    for k in config:
        print(k)


bfs(config)
