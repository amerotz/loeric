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

"""A configuration utility for LOERIC.

It creates new configurations by merging individual configuration snippets.
"""

import argparse
import copy
import importlib.resources as ir
import json
import os
import re

import jsonmerge


def merge_configs(original, new_config):
    base = copy.deepcopy(original)

    base = jsonmerge.merge(base, new_config)

    if "contours" in new_config:
        for c in new_config["contours"]:
            if "recipe" in new_config["contours"][c]:
                base["contours"][c]["recipe"] = new_config["contours"][c]["recipe"]

    if "control_2_contour" in new_config:
        if len(new_config["control_2_contour"]) != 0:
            base["control_2_contour"] = new_config["control_2_contour"]

    return base


def main():
    dir_path = ir.files("loeric.loeric_config")

    # dynamically create folders based on what's available
    dir_path = dir_path / "performance"
    options = os.listdir(dir_path)

    parser = argparse.ArgumentParser()
    for o in options:
        if not os.path.isdir(dir_path / o):
            continue
        name = o.replace("_", "-")
        arg_options = " ".join([val.split(".")[0] for val in os.listdir(dir_path / o)])
        parser.add_argument(
            f"--{name}",
            help=f"Any of: {arg_options}",
            default=[],
            type=str,
            nargs="*",
        )

    # general args
    parser.add_argument(
        "--output",
        help="the output file for this configurations. Defaults to LOERIC internal.",
        default=None,
        type=str,
    )
    args = vars(parser.parse_args())

    # load base config
    with open(dir_path / "base.json", "r") as f:
        base = json.load(f)

    # select files
    config_name = []
    for a in args:
        # skip output and empty args
        if a == "output":
            continue

        # fetch all configs and merge them
        for option in args[a]:
            name = dir_path / f"{a}" / f"{option}.json"
            print("Using", f"{a}/{option}.json")

            with open(name, "r") as f:
                selected = json.load(f)

            base = merge_configs(base, selected)

    if args["output"] is None:
        config_name = dir_path / "config.json"
    else:
        config_name = args["output"]

    with open(config_name, "w") as f:
        print("Saving to", config_name)
        s = json.dumps(base, ensure_ascii=True, indent=4)
        s = re.sub(r"\n +([0-9-\]])", r" \1", s)
        s = re.sub(r"\],\n( +)\[ (?=-*[0-9]+)", r"], [ ", s)
        s = re.sub(r"\[\n( +)\[ (?=-*[0-9]+)", r"[ [ ", s)
        f.write(s)


if __name__ == "__main__":
    main()
