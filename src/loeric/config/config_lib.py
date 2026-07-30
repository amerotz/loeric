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
            if "recipe" in new_config["contours"][c]:
                base["contours"][c]["recipe"] = new_config["contours"][c]["recipe"]

    if "mapper" in new_config:
        base["mapper"]["rules"] = new_config["mapper"]["rules"]

    return base
