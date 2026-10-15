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

import copy
import json

import jsonmerge


def join_configs(configs: list[dict]) -> dict:
    """Merge multiple configuration snippets into one configuration."""
    config = {}
    for c in configs:
        config = merge_configs(config, c)

    return config


def process_config(config):
    """Process configuration variables.

    The ``variables'' object of a configuration allows one to define variables
    once and use them throughout the config. This utility performs a simple
    text-based substitution of the variable name with its value.
    """
    # compile variables by copying them explicitly
    if "variables" in config:
        variables = config["variables"]

        del config["variables"]

        # turn config into string
        dict_string = json.dumps(config)

        for name, value in variables.items():
            dict_string = dict_string.replace(f'"{name}"', json.dumps(value))

        config = json.loads(dict_string)

    # convert modules
    if "groover" in config and "modules" in config["groover"]:
        config["groover"]["modules"] = change_naming_format(
            config["groover"]["modules"]
        )

    if "player" in config and "input" in config["player"]:
        # convert inputs
        config["player"]["input"] = change_naming_format(config["player"]["input"])
        for i in config["player"]["input"]:
            # convert analysers
            if "analysers" in config["player"]["input"][i]:

                config["player"]["input"][i]["analysers"] = change_naming_format(
                    config["player"]["input"][i]["analysers"]
                )

    if "player" in config and "output" in config["player"]:
        # convert inputs
        config["player"]["output"] = change_naming_format(config["player"]["output"])

    return config


def change_naming_format(config: dict):
    """Change naming convection injecting type attributes.

    Change instances of ``"type#name" : {...}`` to
    ``"name": {"type" : ...}`` in the given dictionary.
    """
    keys = list(config)
    for key in keys:
        # get name
        if "#" in key:
            k_type, k_name = key.split("#")
            # if format is module#
            if k_name == "":
                k_name = f"{key}_noname"
        else:
            k_type = key
            k_name = f"{key}_noname"

        config[key]["type"] = k_type
        config[k_name] = config[key]
        del config[key]

    return config


def merge_configs(original, new_config):
    """Merge two configuration files.

    This utility merges configuration files by merging each object in them.
    The contours and mapper rules objects are substituted instead.
    """
    base = copy.deepcopy(original)

    base = jsonmerge.merge(base, new_config)

    if "contours" in new_config:
        for c in new_config["contours"]:
            base["contours"][c] = new_config["contours"][c]

    if "mapper" in new_config:
        base["mapper"]["rules"] = new_config["mapper"]["rules"]

    return base
