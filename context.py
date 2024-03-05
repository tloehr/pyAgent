import coloredlogs
from pathlib import PurePath
from os.path import exists
from os import popen, path
import json
import logging
import io
import sys
from datetime import datetime, timedelta

TRACE = 5


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
            self.configs: {} = json.load(my_config_file)
        self.variables: [str, str] = {}
        self.__timer_listeners = []
        self.__timers: [str, [float, float]] = {}
        self.__WIFI_DEVICE: str = self.configs["network"]["device"]
        self.IPADDRESS = "0.0.0.0"
        self.num_of_reconnects: int = 0
        self.WORKSPACE = workspace
        self.MY_ID: str = self.configs["my_id"]
        self.variables["agentname"] = self.MY_ID
        self.variables["wifi"] = "--"
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
        player_bin: str = self.configs.get("player", {}).get("bin", "")
        self.PLAYER_BIN: str = player_bin if exists(player_bin) else ""
        self.PLAYER_OPTS: str = self.configs.get("player", {}).get("options", "")

        # keep_alive function for those frigging - auto power off bt speakers
        self.BT_KEEP_ALIVE_SOUND: str = self.configs.get("player", {}).get("bt_keep_alive_sound", "")
        self.BT_KEEP_ALIVE_INTERVAL: float = self.configs.get("player", {}).get("bt_keep_alive_interval", 0)

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
            self.log.info('running in a PyInstaller bundle')
        else:
            self.log.info('running in a normal Python process')

        path_to_version: str = path.abspath(path.join(path.dirname(__file__), "version.json"))
        with open(path_to_version) as my_version:
            version: json = json.load(my_version)
            self.variables["agtype"] = "  pyAgent"
            self.variables["agversion"] = version["version"]
            self.variables["agdate"] = version["timestamp"]
            self.variables["agbuild"] = version["buildnumber"]
            self.log.info(f"pyAgent v{version['version']} b{version['buildnumber']}-{version['timestamp']}")

    def reset_stats(self):
        self.num_of_reconnects = 0

    def store_local_ip_address(self):
        ip: str = "0.0.0.0"
        if is_raspberrypi():
            wifi_dev = json.loads(popen(f"nmcli device show {self.__WIFI_DEVICE}|jc --nmcli").read())
            if wifi_dev and "ip4_address_1" in wifi_dev[0]:
                ip = wifi_dev[0]["ip4_address_1"]
        self.IPADDRESS = ip
        self.variables["ip"] = ip

    # def set_variable(self, key: str, var: str):
    #     self.log.trace(f"setting variable {key} to {var}")
    #     self.__variables[key] = var

    def get_current_wifi_signal_strength(self) -> (int, str, str):
        if not is_raspberrypi():
            return 100, "00:00:00:00:00:00", "ssid"
        signal_quality: int = 0
        ap: str = "00:00:00:00:00:00"
        ssid: str = "NO_WIFI"

        # awk workaround for jc to work with nmcli device wifi
        nmcli: str = popen("nmcli -f ACTIVE,SSID,BSSID,SIGNAL device wifi|awk '{if($1 ~ /^yes/) print}'").read()
        if nmcli:
            ap = nmcli.split()[2]
            ssid = nmcli.split()[1]
            signal_quality = int(nmcli.split()[3])  # percent

        self.log.trace(f"Current wifi signal strength: {signal_quality}%")
        self.set_wifi_vars(signal_quality)
        return signal_quality, ssid, ap

    def calculate_timers(self, last_cycle_started_at: float, now: float):
        time_difference_since_last_cycle: float = (now - last_cycle_started_at)
        # fix variables for empty timers
        # and notify listeners if necessary
        for key, value in self.__timers.items():
            if value[1] - time_difference_since_last_cycle < 0:
                self.variables[key] = "--"
                self.__notify_listeners(key_name=key, old_value=value[0], new_value=0)
        # remove all timers that are zero and below
        # OR keep all the others to be precise
        # that's the reason for the >=0 in the comprehension
        self.__timers = {
            k: v for k, v in self.__timers.items()
            if v[1] - time_difference_since_last_cycle >= 0
        }
        # recalculate all timers - remember the timers are values are pairs of floats
        self.__timers = {
            k: [v[0], v[1] - time_difference_since_last_cycle]
            for k, v in self.__timers.items()
        }
        # re-set all variables
        for key, value in self.__timers.items():
            self.log.trace(f"time {key} is now {value[1]}")
            pattern = "%M:%S" if value[1] < 3600000 else "%H:%M:%S"
            new_time_value = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                milliseconds=value[1])
            self.variables[key] = new_time_value.strftime(pattern)
            # this event will be sent out to realize a Progress Bar via the LEDs.
            self.__notify_listeners(key_name=key, old_value=value[0], new_value=value[1])

    def set_timer(self, key: str, time_in_secs: int):
        self.log.trace(f"setting timer {key} to {time_in_secs}")
        # we have to add one second here so the display matches what the player expects to see on the display
        initial_value = (time_in_secs + 1) * 1000
        # left Long = starting value -> never changes
        # right Long = decreasing value ends with 0
        self.__timers[key] = [initial_value, initial_value]

    def clear_timers(self):
        for key in self.__timers.keys():
            self.variables[key] = "--"
        self.__timers.clear()

    def replace_variables(self, line: str) -> str:
        text = line
        for key, value in self.variables.items():
            # log.debug(f"before {text}")
            # log.debug(f"replacing ${{{key}}} with {value}")
            text = text.replace(f"${{{key}}}", str(value))
        # log.debug(f"after {text}")
        return text

    # https://www.educba.com/python-event-handler/
    def __iadd__(self, e_handler):
        self.__timer_listeners.append(e_handler)
        return self

    def __isub__(self, e_handler):
        self.__timer_listeners.remove(e_handler)
        return self

    def __notify_listeners(self, key_name=None, old_value=None, new_value=None):
        for listener in self.__timer_listeners:
            listener(key_name=key_name, old_value=old_value, new_value=new_value)

    def set_wifi_vars(self, signal_quality: int):
        """
        sets the variables for wi-fi signal in percentage and for the LCD (special char is
        user defined in my_lcd.py - hence the \x01 ... \x05 macro)

        :param signal_quality: in percentage
        """
        wifi_symbol: str = "?"  # fallback char
        if signal_quality == 0:
            wifi_symbol = "X"
        if signal_quality > 0:
            wifi_symbol = "\x01"
        if signal_quality >= 20:
            wifi_symbol = "\x02"
        if signal_quality >= 40:
            wifi_symbol = "\x03"
        if signal_quality >= 60:
            wifi_symbol = "\x04"
        if signal_quality >= 80:
            wifi_symbol = "\x05"
        self.variables["wifi"] = f"{signal_quality}%"
        # x00 is the antenna symbol
        self.variables["wifi_signal"] = f"\x00{wifi_symbol}"
