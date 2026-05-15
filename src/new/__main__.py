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
import time

import contour as cnt
import element as le
import groover as gr
import mapper as mp
import matplotlib.pyplot as plt
import player as pl
import tune as tu


def process_config(config):

    # compile variables by copying them explicitly
    if "variables" in config:
        variables = config["variables"]

        del config["variables"]

        # turn config into string
        dict_string = json.dumps(config)

        for name, value in variables.items():
            dict_string = dict_string.replace(f'"{name}"', json.dumps(value))

        config = json.loads(dict_string)

        return config


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


def main(args):

    # load config
    with open(args["config"], "r") as f:
        config_file = json.load(f)
        config_file = process_config(config_file)

    player = pl.Player()

    # load a tune
    mapper = mp.Mapper(config_file["mapper"])
    tune = tu.Tune(args["source"], args["repeat"])
    contour_manager = cnt.ContourManager(config_file["contours"], tune)
    groover = gr.Groover(config_file["modules"])

    if args["plot"] is not None:
        _plot_contours(contour_manager, tune, args["plot"])

    play(tune, player, mapper, groover, contour_manager, args)


def play(tune, player, mapper, groover, contour_manager, args):

    start_time = tune.start_time.eighth_duration

    groover.set_tempo(args["qpm"], start_time)
    player.set_lookahead(groover.lookahead_size)

    # timekeeping
    tick = le.TimeDelta(eighth_duration=start_time - player.lookahead)
    time_division = le.TimeDelta(eighth_duration=2 / le.MINIMUM_QUARTER_DIVISION)

    finish = False

    try:
        while tick < start_time:
            finish = player.step(mapper, contour_manager, groover, tune, tick)
            tick += time_division

        input("Press any key to start")

        # start actual loop
        while not finish:
            start_time = time.time()

            finish = player.step(mapper, contour_manager, groover, tune, tick)

            tick += time_division

            # fraction of eight note converted to seconds
            wait_time = time_division.eighth_duration * player.eighth_duration_seconds

            # compensate loop duration
            delay_time = time.time() - start_time
            wait_time -= delay_time

            # cannot wait negative time
            time.sleep(max(wait_time, 0))

    except KeyboardInterrupt:
        print("Playback terminated.")

    finally:
        player.reset()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", help="the midi file to play.", nargs="?", default="")
    parser.add_argument(
        "-qpm",
        help="the QPM for the tune",
        type=float,
        default=120.0,
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
        help="the path to a configuration file. Every option included in the configuration file will override command line arguments.",
        type=str,
        default=ir.files("loeric.loeric_config.performance").joinpath("config.json"),
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

    main(args)
