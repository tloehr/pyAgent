import coloredlogs
from pathlib import PurePath
from os.path import exists
import json
import logging
import io

TRACE = 5


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kws)


class Context:
    def __init__(self, workspace: str):
        with open(PurePath(workspace, "config.json")) as my_config_file:
            self.configs = json.load(my_config_file)

        self.WORKSPACE = workspace
        self.MY_ID: str = self.configs["my_id"]
        self.mqtt_broker: str = ""
        self.LOG_LEVEL: str = str(self.configs["loglevel"]).upper()
        self.MQTT_ROOT_TOPIC: str = self.configs["mqtt"]["root"]
        self.MQTT_OUTBOUND: str = self.MQTT_ROOT_TOPIC + "/evt/" + self.MY_ID
        self.MQTT_PORT: int = int(self.configs["mqtt"]["port"])
        self.MQTT_INBOUND: str = self.MQTT_ROOT_TOPIC + "/cmd/" + self.MY_ID + "/#"
        self.MQTT_STATUS_QOS: int = int(self.configs["mqtt"]["qos"]["status"])
        self.MQTT_BUTTON_QOS: int = int(self.configs["mqtt"]["qos"]["button"])
        # check if the player bin really exists
        self.PLAYER_BIN: str = self.configs["player"]["bin"] if exists(self.configs["player"]["bin"]) else ""
        self.PLAYER_OPTS: str = self.configs["player"]["options"]

        logging.basicConfig()
        logging.addLevelName(TRACE, "TRACE")

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        fh = logging.FileHandler(PurePath(workspace, "agent.log"))
        fh.setLevel(self.configs["loglevel"])
        fh.setFormatter(formatter)

        # ch = logging.StreamHandler()
        # ch.setLevel(self.configs["loglevel"])
        # ch.setFormatter(formatter)

        self.log = logging.getLogger("mylogger")
        self.log.addHandler(fh)
        # self.log.addHandler(ch)

        # logging.root.setLevel(logging.NOTSET)
        # logging.root.setLevel(level=logging.getLevelName(self.configs["loglevel"]))
        logging.Logger.trace = trace
        coloredlogs.install(level=logging.getLevelName(self.configs["loglevel"]))


# which OS are we running on ?
# if platform.system == "Darwin"

# HOSTNAME = socket.gethostname()
# IPADDR = socket.gethostbyname(HOSTNAME)

def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower():
                return True
    except Exception:
        pass
    return False

# todo: tcpping
