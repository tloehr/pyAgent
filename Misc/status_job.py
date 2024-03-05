import threading, time, json
import paho.mqtt.client as mqtt
import context
from Misc.audio_player import AudioPlayer
from context import Context
from datetime import datetime
from PagedDisplay import my_lcd
from PagedDisplay.my_lcd import MyLCD

EVERY_MINUTE: int = 60
MQTT_STATUS: str = "/status"


class StatusJob(threading.Thread):
    def __init__(self, mqtt_client: mqtt.Client, my_context: Context, audio_player: AudioPlayer):
        self.__audio_player = audio_player
        self.__status_counter: int = 0  # so we send a status on the first run
        self.__bt_wakeup_counter: int = 0
        # self.__my_lcd = my_lcd
        self.__mqtt_client = mqtt_client
        self.__my_context = my_context
        threading.Thread.__init__(self)
        self.start()

    def run(self):
        self.__my_context.log.debug("Status Job starting")
        while True:
            # we update the wi-fi information every 5 seconds
            wifi_info: (int, str, str) = self.__my_context.get_current_wifi_signal_strength()
            self.__my_context.variables["wifi"] = f"{wifi_info[0]}%"
            self.__my_context.log.trace(f"status_counter, MOD12: {self.__status_counter}, {self.__status_counter % 12}")

            if self.__status_counter % 12 == 0:  # 12 loops with a 5 seconds sleep is a minute
                self.send_status(wifi_info)
                self.__audio_player.bt_wakeup()

            self.__bt_wakeup_counter += 1
            self.__status_counter += 1
            time.sleep(5)

    def send_status(self, wifi_info: (int, str, str)):
        if not self.__mqtt_client.is_connected():
            self.__my_context.log.debug("mqtt client is not connected. skipping status()")
            return
        this_status = {
            "version": f"pyAgent {self.__my_context.variables['agversion']}b{self.__my_context.variables['agbuild']}",
            "reconnects": self.__my_context.num_of_reconnects - 1,
            "mqtt-broker": self.__my_context.mqtt_broker,
            "failed_pings": 0,
            "status_counter": self.__status_counter,
            "ip": self.__my_context.IPADDRESS,
            "ap": wifi_info[2],
            "ssid": wifi_info[1],
            "signal_quality": wifi_info[0],
            "timestamp": datetime.now().isoformat()
        }
        self.__my_context.log.debug(f"Sending status #: {self.__status_counter}")
        # self.__check_signal_strength()
        self.__mqtt_client.publish(self.__my_context.MQTT_OUTBOUND + MQTT_STATUS, json.dumps(this_status),
                                   self.__my_context.MQTT_STATUS_QOS, False)
