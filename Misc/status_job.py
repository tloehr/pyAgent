import threading, time, json
import paho.mqtt.client as mqtt
import context
from context import Context
from datetime import datetime
from PagedDisplay import my_lcd
from PagedDisplay.my_lcd import MyLCD

EVERY_MINUTE: int = 60
MQTT_STATUS: str = "/status"


class StatusJob(threading.Thread):
    def __init__(self, mqtt_client: mqtt.Client, my_context: Context):
        self.__loop_counter: int = 12  # so we send a status on the first run
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
            if self.__loop_counter == 12:  # 12 loops with a 5 seconds sleep is a minute
                self.__loop_counter = 0
                self.send_status(wifi_info)
            else:
                self.__loop_counter += 1
            time.sleep(5)

    def send_status(self, wifi_info: (int, str, str)):
        if not self.__mqtt_client.is_connected():
            self.__my_context.log.debug("mqtt client is not connected. skipping status()")
            return
        this_status = {"version": f"pyAgent {self.__my_context.variables['agversion']}b{self.__my_context.variables['agbuild']}",
                       "reconnects": self.__my_context.num_of_reconnects - 1,
                       "mqtt-broker": self.__my_context.mqtt_broker,
                       "failed_pings": 0,
                       "ip": self.__my_context.IPADDRESS,
                       "essid": wifi_info[2],
                       "wifi": wifi_info[1],
                       "timestamp": datetime.now().isoformat()
                       # "remaining_revices":
                       }
        # self.__check_signal_strength()
        self.__mqtt_client.publish(self.__my_context.MQTT_OUTBOUND + MQTT_STATUS, json.dumps(this_status),
                                   self.__my_context.MQTT_STATUS_QOS, False)
