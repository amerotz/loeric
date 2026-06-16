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

import argparse
import importlib.resources as ir
import json
import logging

import matplotlib.pyplot as plt

import loeric.config as lc
import loeric.core.contour as cnt
import loeric.core.groover as gr
import loeric.core.mapper as mp
import loeric.core.player as pl
import loeric.core.tune as tu
import loeric.core.utils as lu

logging.basicConfig(
    level=logging.INFO,
    datefmt="%H:%M:%S",
    format=("[%(levelname)s] " "\033[96m%(name)s\033[0m " "%(message)s"),
)

logging.addLevelName(logging.DEBUG, "\033[90mDEBG\033[0m")
logging.addLevelName(logging.INFO, "\033[94mINFO\033[0m")
logging.addLevelName(logging.WARNING, "\033[93mWARN\033[0m")
logging.addLevelName(logging.ERROR, "\033[91mERRO\033[0m")


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def _plot_contours(manager, tune, plot_keys):

    x = tune.float_times
    pitches = tune.pitches
    x /= max(x)
    plot_num = len(plot_keys)
    fig = plt.figure(figsize=(20, 5 * plot_num))
    axs = fig.subplots(plot_num, 1, sharex=True)
    if plot_num == 1:
        axs = [axs]
    for ax, contour in zip(axs, plot_keys):
        ax.step(
            x,
            (pitches - min(pitches)) / (max(pitches) - min(pitches)),
            linestyle=":",
            where="post",
        )
        ax.step(x, manager.contours[contour].values, where="post", marker="x")
        ax.set_xlim(min(x) - 0.01, 1 + 0.01)
    plt.tight_layout()
    plt.show()


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "-qpm",
        help="the QPM for the tune",
        type=float,
        default=120.0,
    )
    parser.add_argument(
        "-j", "--cores", help="the number of cores to dedicate", type=int, default=None
    )
    parser.add_argument(
        "-r",
        "--repeat",
        help="how many times the tune should be repeated",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--config",
        help="the path to a configuration file.",
        type=str,
        default=ir.files("loeric.config").joinpath("config.json"),
    )
    parser.add_argument(
        "-t",
        "--transpose",
        help="the number of semitones to transpose the tune of",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--plot",
        help="plots the specified contour before playback.",
        nargs="+",
        type=str,
        default=None,
    )

    args = parser.parse_args()
    args = vars(args)

    # load config
    with open(args["config"], "r") as f:
        config_file = json.load(f)
        config_file = lc.process_config(config_file)
        if args["transpose"] is not None and "transpose" in config_file["modules"]:
            config_file["modules"]["transpose"]["steps"] = args["transpose"]

    player = pl.Player(config_file["player"])

    # load a tune
    mapper = mp.Mapper(config_file["mapper"])
    tune = tu.Tune(args["source"], args["repeat"])
    contour_manager = cnt.ContourManager(config_file["contours"], tune)
    groover = gr.Groover(config_file["modules"])

    if args["plot"] is not None:
        _plot_contours(contour_manager, tune, args["plot"])

    # dedicate cores
    if args["cores"] is not None:
        lu.pin_to_cores(range(args["cores"]))

    # realtime priority
    lu.set_realtime_priority()

    lu.play(tune, player, mapper, groover, contour_manager, args)


if __name__ == "__main__":

    main()
