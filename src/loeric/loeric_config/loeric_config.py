import argparse
import jsonmerge
import json
import os


def main():
    dir_path = os.path.dirname(os.path.realpath(__file__))

    parser = argparse.ArgumentParser()
    # loeric args
    parser.add_argument("--tune_type", default=None, type=str)
    parser.add_argument("--instrument", default=None, type=str)
    parser.add_argument("--drone", default=None, type=str)
    parser.add_argument("--ornament", default=None, type=str)
    # shell args
    parser.add_argument("--shell", action="store_true")
    parser.add_argument("--sync_interval", default=1, type=float)
    parser.add_argument("--switch_every", default=16, type=float)
    # general args
    parser.add_argument("--id", default=None, type=str)
    parser.add_argument("--output", default=None, type=str)
    args = vars(parser.parse_args())

    # if configuring the shell
    if args["shell"]:
        dir_path += "/shell"
    else:
        dir_path += "/performance"

    # load base config
    with open(f"{dir_path}/base.json", "r") as f:
        base = json.load(f)

    # which args?
    if args["shell"]:
        folders = []
    else:
        folders = ["tune_type", "instrument", "drone", "ornament"]

    # select files
    config_name = []
    for a in folders:
        if args[a] is None:
            continue
        else:
            for option in args[a].split("-"):
                name = f"{dir_path}/{a}/{option}.json"
                print(name)
                config_name.append(args[a])
                with open(name, "r") as f:
                    selected = json.load(f)
                    base = jsonmerge.merge(base, selected)

    # specific values for shell
    if args["shell"]:
        for name in ["switch_every", "sync_interval"]:
            base[name] = args[name]

    if args["id"] is not None:
        config_name.append(args[a])

    config_name = "_".join(config_name) + ".json"

    if args["output"] is None:
        config_name = f"{dir_path}/config.json"
    else:
        config_name = args["output"]

    with open(config_name, "w") as f:
        print(config_name)
        json.dump(base, f, ensure_ascii=True, indent=4)
