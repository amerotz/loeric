import argparse
import re
import jsonmerge
import json
import os


def main():
    dir_path = os.path.dirname(os.path.realpath(__file__))

    parser = argparse.ArgumentParser()
    # loeric args
    parser.add_argument(
        "--tune-type",
        help="load the configuration to play specific tune types.",
        default=None,
        type=str,
    )
    parser.add_argument(
        "--instrument",
        help="apply a specific instrument model. This includes phrasing, ornamentation, droning configuration etc.",
        default=None,
        type=str,
    )
    parser.add_argument(
        "--drone", help="apply a specific droning model.", default=None, type=str
    )
    parser.add_argument(
        "--ornament",
        help="apply a specific ornamentation model.",
        default=None,
        type=str,
    )
    parser.add_argument(
        "--control",
        help="load a preset for controlling contours and autonomy values.",
        default=None,
        type=str,
    )
    parser.add_argument(
        "--synth",
        help="load a synth preset.",
        default=None,
        type=str,
    )
    # shell args
    parser.add_argument(
        "--shell",
        help="create a configuration file for the Virtual Session shell.",
        action="store_true",
    )
    parser.add_argument(
        "--sync-interval",
        help="the synchronization inteval in the Virtual Session, in eight notes. Default is 1 eight.",
        default=1,
        type=float,
    )
    parser.add_argument(
        "--switch-every",
        help="how often behaviours should change in the Virtual Session, in multiples of the synchronization interval.",
        default=16,
        type=float,
    )
    # general args
    parser.add_argument(
        "--output",
        help="the output file for this configurations. Defaults to LOERIC's internal storage. If a path is specified, the configuration will be saved, but not loaded in LOERIC.",
        default=None,
        type=str,
    )
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
        folders = [
            "ornament",
            "instrument",
            "tune_type",
            "drone",
            "control",
            "synth",
        ]

    # select files
    config_name = []
    for a in folders:
        if args[a] is None:
            continue
        else:
            for option in args[a].split("-"):
                name = f"{dir_path}/{a}/{option}.json"
                print("Using", f"{a}/{option}.json")
                config_name.append(args[a])
                with open(name, "r") as f:
                    selected = json.load(f)
                    base = jsonmerge.merge(base, selected)

                    if "contours" in selected:
                        for c in selected["contours"]:
                            if "recipe" in selected["contours"][c]:
                                base["contours"][c]["recipe"] = selected["contours"][c]["recipe"]

    # specific values for shell
    if args["shell"]:
        for name in ["switch_every", "sync_interval"]:
            base[name] = args[name]

    config_name = "_".join(config_name) + ".json"

    if args["output"] is None:
        config_name = f"{dir_path}/config.json"
    else:
        config_name = args["output"]

    with open(config_name, "w") as f:
        print("Saving to", config_name)
        s = json.dumps(base, ensure_ascii=True, indent=4)
        s = re.sub(r"\n +([0-9-\]])", r" \1", s)
        s = re.sub(r"\],\n( +)\[ (?=-*[0-9]+)", r"], [ ", s)
        s = re.sub(r"\[\n( +)\[ (?=-*[0-9]+)", r"[ [ ", s)
        f.write(s)
