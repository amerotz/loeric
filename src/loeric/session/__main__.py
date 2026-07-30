import argparse
import importlib.resources as ir
import json
import logging

import loeric.session.session as ls

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    # open config
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "-qpm",
        help="the QPM for the tune",
        type=float,
        default=120.0,
    )
    parser.add_argument(
        "--config",
        help="the path to a configuration file.",
        type=str,
        default=ir.files("loeric.config").joinpath("config.json"),
    )

    args = parser.parse_args()
    args = vars(args)

    with open(args["config"], "r") as f:
        config_file = json.load(f)

    # create Session object
    session = ls.Session(config_file)
    session.set_tempo(args["qpm"])

    # start Session
    session.start(wait_for_prompt=True)

    # stop session
    session.stop()
