import json
import sys
from datetime import datetime
from pathlib import PurePath
from os.path import exists
from agent import Agent


def main(args=None):
    """The main routine."""
    if args is None:
        args = sys.argv[1:]
    if len(args) < 1:
        print("specify the working directory")
        exit(1)
    if "in_development" in args:
        buildnumber()
    Agent(args)


# def exit_handler(signum, frame):
#     print("Exiting...")

def buildnumber():
    """
    increases buildnumber and sets timestamp for version file
    but only when running on development machine
    :return:
    """
    version: json
    with open(PurePath("version.json")) as read_version:
        version = json.load(read_version)
        version["buildnumber"] += 1
        version["timestamp"] = datetime.now().strftime("%Y%d%m-%H%M%S")
    with open(PurePath("version.json"), "w") as write_version:
        write_version.write(json.dumps(version, indent=4))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
