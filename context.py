import socket
from subprocess import Popen, PIPE
import re
import coloredlogs
from pathlib import PurePath
from os.path import exists
from os import popen
import json
import logging
import io

TRACE = 5

# STATICS
WIFI_PERFECT: int = -30
WIFI_EXCELLENT: int = -50
WIFI_GOOD: int = -60
WIFI_FAIR: int = -67
WIFI_MINIMUM: int = -70
WIFI_UNSTABLE: int = -80
WIFI_BAD: int = -90
NO_WIFI: int = -99
WIFI: list[str] = ["NO_WIFI", "BAD", "FAIR", "GOOD", "PERFECT"]


def is_raspberrypi():
    try:
        with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
            if 'raspberry pi' in m.read().lower():
                return True
    except Exception:
        pass
    return False


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kws)


class Context:
    def __init__(self, workspace: str):
        with open(PurePath(workspace, "config.json")) as my_config_file:
            self.configs = json.load(my_config_file)

        self.__WIFI_DEVICE: str = self.configs["network"]["device"]
        self.IPADDRESS = self.__get_local_ip_address()
        self.num_of_reconnects: int = 0
        self.WORKSPACE = workspace
        self.MY_ID: str = self.configs["my_id"]
        self.LOW_TRIGGER: [str] = self.configs["hardware"]["triggered_on_low"]
        self.mqtt_broker: str = ""
        self.LOG_LEVEL: str = str(self.configs["loglevel"]).upper()
        self.MQTT_ROOT_TOPIC: str = self.configs["network"]["mqtt"]["root"]
        self.MQTT_OUTBOUND: str = self.MQTT_ROOT_TOPIC + "/evt/" + self.MY_ID
        self.MQTT_PORT: int = int(self.configs["network"]["mqtt"]["port"])
        self.MQTT_INBOUND: str = self.MQTT_ROOT_TOPIC + "/cmd/" + self.MY_ID + "/#"
        self.MQTT_STATUS_QOS: int = int(self.configs["network"]["mqtt"]["qos"]["status"])
        self.MQTT_BUTTON_QOS: int = int(self.configs["network"]["mqtt"]["qos"]["button"])
        self.MQTT_RFID_QOS: int = int(self.configs["network"]["mqtt"]["qos"]["rfid"])
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

    def reset_stats(self):
        self.num_of_reconnects = 0

    def __get_local_ip_address(self) -> str:
        ip: str = "0.0.0.0"
        if is_raspberrypi():
            wifi_dev = json.loads(popen(f"nmcli device show {self.__WIFI_DEVICE}|jc --nmcli").read())
            if wifi_dev:
                ip = wifi_dev[0]["ip4_address_1"]
        return ip


def get_current_wifi_signal_strength() -> (int, str, str):
    if not is_raspberrypi():
        return 100, "00:00:00:00:00:00", "ssid"
    signal = 0
    mac = "00:00:00:00:00:00"
    ssid = "NO_WIFI"
    wifi_devices = json.loads(popen("nmcli device wifi|jc --nmcli").read())
    for ap in wifi_devices:
        if ap["in_use"] == "*":
            mac = ap["bssid"]
            signal = ap["signal"]
            ssid = ap["ssid"]
            continue
    return signal, mac, ssid
