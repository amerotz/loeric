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

new_config = {}

# variables
if "variables" in config:
    new_config["variables"] = config["variables"]
    del config["variables"]

# process contours
if "contours" in config:
    new_config["contours"] = {}
    for c in config["contours"]:
        if "human_impact_scale" in config["contours"][c]:
            if "mapper" not in new_config:
                new_config["mapper"] = {}
            if "rules" not in new_config["mapper"]:
                new_config["mapper"]["rules"] = []
            new_config["mapper"]["rules"].append(
                f'{config["contours"][c]["human_impact_scale"]} : %{c}'
            )
            del config["contours"][c]["human_impact_scale"]
        if len(config["contours"][c]) != 0:
            new_config["contours"][c] = config["contours"][c]
    del config["contours"]

modulated = []
# interaction
if "control_2_contour" in config:
    if "player" not in new_config:
        new_config["player"] = {}
    if "input" not in new_config["player"]:
        new_config["player"]["input"] = {"main": {"active": True, "controls": {}}}
    if "mapper" not in new_config:
        new_config["mapper"] = {}
    if "rules" not in new_config["mapper"]:
        new_config["mapper"]["rules"] = []
    if "sources" not in new_config["mapper"]:
        new_config["mapper"]["sources"] = []
    for name in config["control_2_contour"]:
        for c in config["control_2_contour"][name]["contours"]:
            new_config["player"]["input"]["main"]["controls"][c] = config[
                "control_2_contour"
            ][name]["control"]

            chopped = c.split("_")
            if chopped[-1] == "intensity":
                basename = "".join(chopped[:-1])
                new_config["mapper"]["rules"].append(f"{c} ~ {basename}")
                new_config["mapper"]["sources"].append(c)
                new_config["mapper"]["sources"].append(basename)
                modulated.append(basename)

            elif chopped[0] == "orn" and chopped[-1] == "prob":
                modulated.append(c)

            elif chopped[0] == "orn":
                modulated.append(c)

    del config["control_2_contour"]

if "values" in config:
    min_v = 1
    max_v = 127
    if "min_velocity" in config["values"]:
        min_v = config["values"]["min_velocity"]
        del config["values"]["min_velocity"]
    if "max_velocity" in config["values"]:
        max_v = config["values"]["max_velocity"]
        del config["values"]["max_velocity"]

    if "player" not in new_config:
        new_config["player"] = {}
    if "output" not in new_config["player"]:
        new_config["player"]["output"] = {}
    if "main" not in new_config["player"]["output"]:
        new_config["player"]["output"]["main"] = {}

    new_config["player"]["output"]["main"]["velocity_range"] = [min_v, max_v]

    if len(config["values"]) == 0:
        del config["values"]


# sections
for section in ["swing", "legato"]:
    if section in config:
        if "modules" not in new_config:
            new_config["modules"] = {}

        new_config["modules"][section] = config[section]
        if config[section]["bind"] in modulated:
            new_config["modules"][section]["bind"] = (
                "$" + new_config["modules"][section]["bind"]
            )
        del config[section]

# drone
if "drone" in config:
    if "modules" not in new_config:
        new_config["modules"] = {}
    new_config["modules"]["drones"] = {}

    if "active" in config["drone"]:
        new_config["modules"]["drones"]["bypass"] = config["drone"]["active"]
    del config["drone"]["active"]

    if len(config["drone"]) == 0:
        del config["drone"]

# tempo
if "tempo_control" in config:
    if "modules" not in new_config:
        new_config["modules"] = {}
    new_config["modules"]["timing"] = {}

    if "tempo_warp_bpms" in config["tempo_control"]:
        new_config["modules"]["timing"]["qpm_amount"] = config["tempo_control"][
            "tempo_warp_bpms"
        ]
    del config["tempo_control"]["tempo_warp_bpms"]

    if len(config["tempo_control"]) == 0:
        del config["tempo_control"]

# ornament
if "ornamentation" in config:
    if "modules" not in new_config:
        new_config["modules"] = {}
    new_config["modules"]["ornament"] = {"data": config["ornamentation"]}

    for o in new_config["modules"]["ornament"]["data"]:
        if f"orn_{o}_prob" in modulated:
            new_config["modules"]["ornament"]["data"][o][
                "probability_contour"
            ] = f"orn_{o}_prob"
        if f"orn_{o}" in modulated:
            new_config["modules"]["ornament"]["data"][o]["bind"] = f"orn_{o}"

    del config["ornamentation"]


print(json.dumps(new_config))
print()
print(config)
