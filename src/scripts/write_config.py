import argparse
import jsonmerge
import json

parser = argparse.ArgumentParser()
parser.add_argument("--id", default=None, type=str)
parser.add_argument("--tune_type", default=None, type=str)
parser.add_argument("--instrument", default=None, type=str)
args = vars(parser.parse_args())

# load base config
with open("config_maker/base.json", "r") as f:
    base = json.load(f)

# select files
config_name = []
for a in args:
    if args[a] is None:
        continue
    elif a == "id":
        config_name.append(args[a])
        continue
    name = f"config_maker/{a}/{args[a]}.json"
    print(name)
    config_name.append(args[a])
    with open(name, "r") as f:
        selected = json.load(f)
        base = jsonmerge.merge(base, selected)

config_name = "_".join(config_name) + ".json"
with open(config_name, "w") as f:
    print(config_name)
    json.dump(base, f, ensure_ascii=True, indent=4)
