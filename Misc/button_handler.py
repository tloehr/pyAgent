import json

from context import Context
from gpiozero import Button
import paho.mqtt.client as mqtt

MQTT_REPORT_EVENT: str = "/status"


class ButtonHandler:
    def __init__(self, mqtt_client: mqtt.Client, my_context: Context):
        self.__my_context = my_context
        self.__mqtt_client = mqtt_client
        gpio_btn01: str = self.__my_context.configs["hardware"]["buttons"]["btn01"]
        # debounce: float = self.__my_context.configs["hardware"]["buttons"]["debounce"]
        gpio_btn02: str = self.__my_context.configs["hardware"]["buttons"]["btn02"]
        self.__btn01 = Button(gpio_btn01)
        self.__btn02 = Button(gpio_btn02)
        self.__btn01.when_pressed = self.__pressed_btn01
        self.__btn01.when_released = self.__released_btn01
        self.__btn02.when_pressed = self.__pressed_btn02
        self.__btn02.when_released = self.__released_btn02

    def __pressed_btn01(self):
        self.__report_event("btn01", "down")

    def __released_btn01(self):
        self.__report_event("btn01", "up")

    def __pressed_btn02(self):
        self.__report_event("btn02", "down")

    def __released_btn02(self):
        self.__report_event("btn02", "up")

    def __report_event(self, button: str, state: str):
        if not self.__mqtt_client.is_connected():
            return
        event = {"button": state}
        self.__my_context.log.debug(f"{button} {state}")
        self.__mqtt_client.publish(self.__my_context.MQTT_OUTBOUND + "/" + button, json.dumps(event),
                                   self.__my_context.MQTT_BUTTON_QOS, True)
