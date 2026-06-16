import copy
import json

import jsonmerge


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
