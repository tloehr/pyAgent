import socket
from subprocess import Popen, PIPE
import re
import coloredlogs
from pathlib import PurePath
from os.path import exists
from os import popen, path
import json
import logging
import io
import sys

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
        self.variables: [str, str] = {}

        self.__WIFI_DEVICE: str = self.configs["network"]["device"]
        self.IPADDRESS = self.__get_local_ip_address()
        self.num_of_reconnects: int = 0
        self.WORKSPACE = workspace
        self.MY_ID: str = self.configs["my_id"]
        self.variables["agentname"] = self.MY_ID
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
        # LOGGER SETUP
        logging.basicConfig()
        logging.addLevelName(TRACE, "TRACE")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh = logging.FileHandler(PurePath(workspace, "agent.log"))
        fh.setLevel(self.configs["loglevel"])
        fh.setFormatter(formatter)
        self.log = logging.getLogger("mylogger")
        self.log.addHandler(fh)
        logging.Logger.trace = trace
        coloredlogs.install(level=logging.getLevelName(self.configs["loglevel"]))

        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            print('running in a PyInstaller bundle')
        else:
            print('running in a normal Python process')

        #
        path_to_version: str = path.abspath(path.join(path.dirname(__file__), "version.json"))
        with open(path_to_version) as my_version:
            version: json = json.load(my_version)
            self.variables["agversion"] = version["version"]
            self.variables["agdate"] = version["timestamp"]
            self.variables["agbuild"] = version["buildnumber"]
            self.log.info(f"pyAgent v{version['version']} b{version['buildnumber']}-{version['timestamp']}")

    def reset_stats(self):
        self.num_of_reconnects = 0

    def __get_local_ip_address(self) -> str:
        ip: str = "0.0.0.0"
        if is_raspberrypi():
            wifi_dev = json.loads(popen(f"nmcli device show {self.__WIFI_DEVICE}|jc --nmcli").read())
            if wifi_dev and "ip4_address_1" in wifi_dev[0]:
                ip = wifi_dev[0]["ip4_address_1"]
        return ip

    # def set_variable(self, key: str, var: str):
    #     self.log.trace(f"setting variable {key} to {var}")
    #     self.__variables[key] = var

    def get_current_wifi_signal_strength(self) -> (int, str, str):
        if not is_raspberrypi():
            return 100, "00:00:00:00:00:00", "ssid"
        signal = 0
        mac = "00:00:00:00:00:00"
        ssid = "NO_WIFI"

        # awk workaround for jc to work with nmcli device wifi
        nmcli: str = popen("nmcli -f ACTIVE,SSID,BSSID,SIGNAL device wifi|awk '{if($1 ~ /^yes/) print}'").read()
        if nmcli:
            mac = nmcli.split()[1]
            ssid = nmcli.split()[2]
            signal = int(nmcli.split()[3])

        self.log.debug(f"Current wifi signal strength: {signal}%")

        return signal, mac, ssid
