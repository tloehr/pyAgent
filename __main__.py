import sys
from agent import Agent
import atexit


def main(args=None):
    """The main routine."""
    if args is None:
        args = sys.argv[1:]
    if len(args) < 1:
        print("specify the working directory")
        exit(1)
    Agent(args)


# def exit_handler(signum, frame):
#     print("Exiting...")


if __name__ == "__main__":
    # atexit.register(exit_handler)
    sys.exit(main(sys.argv))
