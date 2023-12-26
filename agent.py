import copy

import context
from Misc.rfid_handler import RfidHandler
from PinHandler.pin_handler import PinHandler
from PagedDisplay.my_lcd import MyLCD
from Misc.status_job import StatusJob
from Misc.audio_player import AudioPlayer
import json
from context import Context, is_raspberrypi
import time
import paho.mqtt.client as mqtt

if is_raspberrypi():
    from Misc import button_handler, rfid_handler

# WORKSPACE = sys.args[1]
NET_STATUS: [str, str] = {"led_all": "off", "wht": "netstatus"}
# PROGRESS_SCHEMES: [str] = ["", "normal", "normal", "fast", "very_fast", "mega_fast", "mega_fast"]
PROGRESS_ESCALATION = [
    [["wht"], "normal"],
    [["wht"], "fast"],
    [["wht"], "very_fast"],
    [["wht", "red"], "normal"],
    [["wht", "red"], "fast"],
    [["wht", "red"], "very_fast"],
    [["wht", "red", "ylw"], "normal"],
    [["wht", "red", "ylw"], "fast"],
    [["wht", "red", "ylw"], "very_fast"],
    [["wht", "red", "ylw", "grn"], "normal"],
    [["wht", "red", "ylw", "grn"], "fast"],
    [["wht", "red", "ylw", "grn"], "very_fast"],
    [["wht", "red", "ylw", "grn", "blu"], "fast"],
    [["wht", "red", "ylw", "grn", "blu"], "very_fast"],
    [["wht", "red", "ylw", "grn", "blu"], "mega_fast"],
]


class Agent:

    def __init__(self, args):
        self.__mqtt_client: mqtt.Client = None
        # contains the timer name when progress runs - empty otherwise
        self.__progress_bar: str = ""
        self.__previous_step: int = -1
        self.WORKSPACE = args[1]
        self.__my_context: Context = Context(self.WORKSPACE)
        self.__my_pin_handler = PinHandler(self.__my_context)
        self.__lcd = MyLCD(self.__my_context)
        self.__lcd.set_variable("ip", self.__my_context.IPADDRESS)
        # for the progress bar function
        self.__lcd += self.__on_timer_changed

        self.__init_mqtt()
        if is_raspberrypi():
            button_handler.ButtonHandler(self.__mqtt_client, self.__my_context)
            self.__rfid_handler = RfidHandler(self.__mqtt_client, self.__my_context)

        self.__my_audio_player: AudioPlayer = AudioPlayer(self.__my_context)
        self.__my_status_job = StatusJob(self.__mqtt_client, self.__my_context)  # start the status job
        self.__my_status_job.send_status()

    def __init_mqtt(self):
        # Searching for a valid MQTT broker. Several addresses can be specified in the ~/.pyagent/config.json file
        # the agent will try them out until can establish a connection
        # then this broker will be kept
        current_broker: int = 0
        mqtt_broker: str = ""
        self.__mqtt_client = mqtt.Client()
        self.__mqtt_client.max_inflight_messages_set(self.__my_context.configs["network"]["mqtt"]["max_inflight"])
        self.__mqtt_client._clean_session = self.__my_context.configs["network"]["mqtt"]["clean_session"]

        self.__pre_init_page()

        while not self.__mqtt_client.is_connected():
            mqtt_broker = self.__my_context.configs["network"]["mqtt"]["broker"][current_broker]
            try:
                self.__my_context.log.info(f"trying broker: '{mqtt_broker}'")
                self.__lcd.set_variable("broker", mqtt_broker)
                self.__mqtt_client.on_connect = self.on_connect
                self.__mqtt_client.on_message = self.on_message
                self.__mqtt_client.on_disconnect = self.on_disconnect
                self.__mqtt_client.connect(mqtt_broker, self.__my_context.MQTT_PORT)
                self.__mqtt_client.loop_start()
                time.sleep(2)
            except OSError as os_ex:
                current_broker += 1
                if current_broker >= len(self.__my_context.configs["network"]["mqtt"]["broker"]):
                    current_broker = 0
                self.__my_context.log.info("couldn't connect to mqtt - trying next one")

                # show current WI-FI signal strength on the led bar
                net_status: [str, str] = copy.deepcopy(NET_STATUS)
                wifi_info: (int, str, str) = context.get_current_wifi_signal_strength()
                signal_quality = wifi_info[0]
                if signal_quality >= 20:
                    net_status["red"] = "netstatus"
                if signal_quality >= 40:
                    net_status["ylw"] = "netstatus"
                if signal_quality >= 60:
                    net_status["grn"] = "netstatus"
                if signal_quality >= 80:
                    net_status["blu"] = "netstatus"
                self.__my_pin_handler.proc_pins(net_status)
                self.__lcd.set_variable("wifi", f"{signal_quality}%")
                time.sleep(2)

        self.__my_context.MQTT_BROKER = mqtt_broker
        # self.__lcd.set_variable("broker", mqtt_broker)
        net_status: [str, str] = copy.deepcopy(NET_STATUS)
        net_status["blu"] = "netstatus"
        self.__my_pin_handler.proc_pins(net_status)
        self.__post_init_page()

    def __post_init_page(self):
        self.__lcd.proc_paged({"page0": [
            "I am ${agentname}",
            "pyAgent ${agversion}b${agbuild}",
            "broker: ${broker}",
            "WiFi: ${wifi}"
        ]})

    def __pre_init_page(self):
        self.__lcd.proc_paged({"page0": [
            "${agentname} ==> ${broker}",
            "pyAgent ${agversion}b${agbuild}",
            "${ip}",
            "WiFi: ${wifi}"
        ]})

    def on_connect(self, client, userdata, flags, rc):
        self.__my_context.log.info("Connected with result code " + str(rc))
        self.__my_context.num_of_reconnects += 1
        self.__mqtt_client.subscribe(self.__my_context.MQTT_INBOUND)
        net_status = NET_STATUS
        net_status["blu"] = "netstatus"
        self.__my_pin_handler.proc_pins(net_status)

    def __on_timer_changed(self, key_name, old_value, new_value):
        self.__my_context.log.trace(f"{key_name}: {old_value} -> {new_value}")
        if self.__progress_bar != key_name:
            return
        if new_value == 0:
            self.__progress_bar = ""
            self.__my_pin_handler.proc_pins({"led_all": "very_long"})  # one last signal, then off
            return
        ratio: float = 1 - new_value / old_value
        progress_steps: int = len(PROGRESS_ESCALATION) - 1
        step: int = round(ratio * progress_steps)
        self.__my_context.log.trace(f"Progress: {round(ratio * 100, 2)}%")
        if step == self.__previous_step:  # only set LEDs when necessary
            return
        self.__previous_step = step
        # construct a pin handler scheme
        pins = PROGRESS_ESCALATION[step][0]
        speed = PROGRESS_ESCALATION[step][1]
        self.__my_context.log.trace(f"{step}: {pins} -> {speed}")
        # comprehension to construct a json for the pin_handler
        my_scheme = {pin: speed for pin in pins}
        self.__my_context.log.trace(my_scheme)
        self.__my_pin_handler.proc_pins(my_scheme)

    def on_disconnect(self, my_client, userdata, msg):
        self.__my_context.log.info("disconnected")
        self.__my_pin_handler.proc_pins(NET_STATUS)

    def on_message(self, my_client, userdata, msg):
        # "normal", "normal", "fast", "fast", "very_fast"
        try:
            cmd = msg.topic.rsplit('/', 1)[1]
            self.__my_context.log.warning(f"received '{msg.payload}' from '{msg.topic}' cmd '{cmd}'")
            params_json = json.loads(msg.payload.decode('UTF-8'))
            match cmd:
                case "visual":
                    """
                        /visual/ {"progress": "remaining"}
                        only useful in combination with a timer of the same name - see below                        
                        will use the leds to show the time progression "remaining"
                    """
                    if "progress" in params_json:
                        self.__my_pin_handler.leds_off()
                        self.__progress_bar = params_json["progress"]
                        self.__previous_step = -1
                    else:
                        self.__my_pin_handler.proc_pins(params_json)
                        self.__progress_bar = ""
                case "acoustic":
                    self.__my_pin_handler.proc_pins(params_json)
                case "paged":
                    self.__lcd.proc_paged(params_json)
                case "play":
                    self.__my_audio_player.proc_play(params_json)
                case "rfid":
                    """
                        sets the mode how to handle rfid events
                        {
                            "mode": "revive_player" | "report_uid" | "reset_lives"
                        }
                    """
                    if is_raspberrypi():
                        self.__rfid_handler.proc_rfid(params_json)
                case "timers":
                    """
                        /timer/ {"remaining": 120}
                        timer variables can be used on the LCD screen as 
                        ${variables} with a autoformat like mm:ss or hh:mm:ss 
                    """
                    if "_clearall" in params_json.keys():
                        # removes all timers
                        self.__lcd.clear_timers()
                    else:
                        for key, value in params_json.items():
                            self.__lcd.set_timer(key, value)
                case "vars":
                    for key, value in params_json.items():
                        self.__lcd.set_variable(key, value)
                case "reset_status":
                    self.__my_context.reset_stats()
                case "status":
                    self.__my_status_job.send_status()
                case _:
                    self.__my_context.log.warning(f"got command '{cmd}' but don't know what to do with it")
        except Exception as ex:
            message = "An exception of type {0} occurred. Arguments:\n{1!r}".format(type(ex).__name__, ex.args)
            self.__my_context.log.warning(f"oh shit: {message}")
