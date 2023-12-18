import sys
from agent import Agent


def main(args=None):
    """The main routine."""
    if args is None:
        args = sys.argv[1:]
    if len(args) < 1:
        print("specify the working directory")
        exit(1)
    Agent(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
