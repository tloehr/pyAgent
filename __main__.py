import json
import sys
import traceback
from datetime import datetime
from pathlib import PurePath
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
    sys.excepthook = custom_excepthook
    Agent(args)


def custom_excepthook(exc_type, exc_value, exc_traceback):
    # Do not print exception when user cancels the program
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    print("An uncaught exception occurred:")
    print(f"Type: {exc_type}", file=sys.stderr)
    print(f"Value: {exc_value}", file=sys.stderr)

    if exc_traceback:
        format_exception = traceback.format_tb(exc_traceback)
        for line in format_exception:
            print(repr(line))


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
        version["timestamp"] = datetime.now().strftime("%y%m%d-%H%M")
    with open(PurePath("version.json"), "w") as write_version:
        write_version.write(json.dumps(version, indent=4))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
