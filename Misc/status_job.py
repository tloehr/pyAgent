import threading, time, json
import paho.mqtt.client as mqtt
from context import Context
from datetime import datetime

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
EVERY_MINUTE: int = 60
MQTT_STATUS: str = "/status"


class StatusJob(threading.Thread):
    def __init__(self, mqtt_client: mqtt.Client, my_context: Context):
        self.__mqtt_client = mqtt_client
        self.__my_context = my_context
        self.num_of_reconnects: int = 0
        self.sum_of_failed_pings: int = 0
        threading.Thread.__init__(self)
        self.start()

    def run(self):
        self.__my_context.log.debug("Status Job starting")
        while True:
            self.send_status()
            time.sleep(EVERY_MINUTE)

    def reset_stats(self):
        self.num_of_reconnects = 0
        self.sum_of_failed_pings = 0

    def __get_wifi_quality_str(self, percent: str) -> str:
        level: int = int(percent.split('=|/')[1])
        quality: int = min(100, abs(level))
        wifi_quality: int = min(4, int(quality / 25 + 1))
        self.__my_context.log.trace(f"{level}% is signal quality {WIFI[wifi_quality]}")
        return WIFI[wifi_quality]

    def __get_wifi_quality_int(self, dbm: int) -> str:
        if dbm >= 0:
            wifi_quality = 0
        elif dbm > WIFI_EXCELLENT:
            wifi_quality = 4  # PERFECT
        elif dbm > WIFI_GOOD:
            wifi_quality = 3  # good
        elif dbm > WIFI_FAIR:
            wifi_quality = 2  # fair
        elif dbm > WIFI_MINIMUM:
            wifi_quality = 2  # fair
        elif dbm > WIFI_UNSTABLE:
            wifi_quality = 1  # bad
        elif dbm > WIFI_BAD:
            wifi_quality = 1  # bad
        else:
            wifi_quality = 0  # no wifi
        self.__my_context.log.trace(f"{dbm} dbm signal quality {WIFI[wifi_quality]}")
        return WIFI[wifi_quality]

    def send_status(self):
        if not self.__mqtt_client.is_connected():
            self.__my_context.log.debug("mqtt client is not connected. skipping status()")
            return
        this_status = {"version": "pyAgent v1.0",
                       "reconnects": self.num_of_reconnects - 1,
                       "mqtt-broker": self.__my_context.mqtt_broker,
                       "failed_pings": self.sum_of_failed_pings,
                       "ip": "asd",  # context.IPADDR,
                       "rssi": "-49",
                       "wifi": "good",
                       "timestamp": datetime.now().isoformat()
                       }
        self.__mqtt_client.publish(self.__my_context.MQTT_OUTBOUND + MQTT_STATUS, json.dumps(this_status),
                                   self.__my_context.MQTT_STATUS_QOS, False)
