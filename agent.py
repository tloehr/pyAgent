import signal
import sys

from Misc.rfid_handler import RfidHandler
from PinHandler.pin_handler import PinHandler
from PagedDisplay.my_lcd import MyLCD
from Misc.status_job import StatusJob
from Misc.audio_player import AudioPlayer
import json
from uuid import uuid4
from context import Context, is_raspberrypi
import time
import paho.mqtt.client as mqtt

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
        self.__prev_signal_quality: int = -1
        # contains the timer name when progress runs - empty otherwise
        self.__progress_bar: str = ""
        self.__previous_step: int = -1
        # we keep track on our own because of this
        # https://github.com/eclipse/paho.mqtt.python/issues/525
        self.__connected: bool = False
        self.WORKSPACE = args[1]
        self.__my_context: Context = Context(self.WORKSPACE)
        self.__my_pin_handler = PinHandler(self.__my_context)
        self.__lcd = MyLCD(self.__my_context)
        self.__my_context.variables["broker"] = "-none-"
        self.__my_context.store_local_ip_address()
        # for the progress bar function
        self.__my_context += self.__on_timer_changed
        self.__my_audio_player: AudioPlayer = AudioPlayer(self.__my_context)
        self.__received_first_visual_led_msg_already = False
        self.__received_first_paged_msg_already = False
        self.__init_mqtt()
        if is_raspberrypi():
            from Misc import button_handler
            button_handler.ButtonHandler(self.__mqtt_client, self.__my_context)
            self.__rfid_handler = RfidHandler(self.__mqtt_client, self.__my_context)
        self.__my_status_job = StatusJob(self.__mqtt_client, self.__my_context, self.__my_audio_player, self.__rfid_handler.active)  # start the status job
        signal.signal(signal.SIGTERM, self.__shutdown)

    def __shutdown(self, signum, frame):
        print("Shutting down...")
        self.__my_context.log.debug(f"signum={signum}, frame={frame}")
        self.__my_context.log.info("Shutting down")
        self.__my_pin_handler.leds_off()
        self.__my_pin_handler.sirens_off()
        self.__my_audio_player.stop_all()
        self.__lcd.proc_paged({"page0": [
            "",
            "AGENT SHUTTING DOWN",
            "",
            "   BYE BYE...."
        ]})
        time.sleep(2)
        sys.exit()

    def __init_mqtt(self):
        # Searching for a valid MQTT broker. Several addresses can be specified in the ~/.pyagent/config.json file
        # the agent will try them out until can establish a connection
        # then this broker will be kept
        self.__mqtt_client = mqtt.Client(clean_session=self.__my_context.configs["network"]["mqtt"]["clean_session"],
                                         client_id=self.__my_context.MY_ID + str(uuid4()))
        self.__mqtt_client.max_inflight_messages_set(self.__my_context.configs["network"]["mqtt"]["max_inflight"])
        self.__mqtt_client.on_connect = self.on_connect
        self.__mqtt_client.on_disconnect = self.on_disconnect
        self.__mqtt_client.on_message = self.on_message
        self.__search_for_broker()
        self.__post_init_page()

    def __post_init_page(self):
        if self.__received_first_paged_msg_already:
            return
        self.__lcd.proc_paged({"page0": [
            "I am ${agentname}",
            "pyAgent ${agversion}b${agbuild}",
            "broker: ${broker}",
            "WiFi: ${wifi}  ${wifi_signal}"
        ]})

    def __pre_init_page(self):
        self.__lcd.proc_paged({"page0": [
            "${agentname} ==> ${broker}",
            "pyAgent ${agversion}b${agbuild}",
            "${ip}",
            "WiFi: ${wifi}  ${wifi_signal}"
        ]})

    def on_connect(self, client, userdata, flags, rc):
        self.__connected = True
        self.__my_context.log.info("Connected to mqtt broker")
        self.__my_context.num_of_reconnects += 1
        self.__mqtt_client.subscribe(self.__my_context.MQTT_INBOUND)
        # store local ip address
        self.__my_context.store_local_ip_address()
        if not self.__received_first_visual_led_msg_already:
            net_status: [str, str] = {"wht": "signal_strength",
                                      "red": "off",
                                      "ylw": "off",
                                      "grn": "off",
                                      "blu": "signal_strength"}
            self.__my_pin_handler.proc_pins(net_status)

    def __on_timer_changed(self, key_name, old_value, new_value):
        self.__my_context.log.debug(f"{key_name}: {old_value} -> {new_value}")
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
        self.__connected = False
        self.__my_context.log.info("disconnected")
        while not self.__connected:
            time.sleep(2)
            try:
                self.__my_context.log.debug("trying to reconnect")
                if not self.__lcd.is_lcd_is_in_use():
                    self.__render_signal_quality(self.__my_context.get_current_wifi_signal_strength()[0])
                self.__mqtt_client.reconnect()
                self.__connected = True
            except OSError as ose:
                self.__connected = False
                self.__my_context.log.debug(f"error while trying to reconnect - {ose}")

    def on_message(self, my_client, userdata, msg):
        # "normal", "normal", "fast", "fast", "very_fast"
        try:
            cmd = msg.topic.rsplit('/', 1)[1]
            self.__my_context.log.debug(f"received '{msg.payload}' from '{msg.topic}' cmd '{cmd}'")
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
                    self.__received_first_visual_led_msg_already = True
                case "acoustic":
                    self.__my_pin_handler.proc_pins(params_json)
                case "paged":
                    self.__lcd.proc_paged(params_json)
                    self.__received_first_paged_msg_already = True
                case "play":
                    self.__my_audio_player.proc_play(params_json)
                case "rfid":
                    """
                        sets the mode how to handle rfid events
                        {
                            "mode": "mobile_spawn", "max_spawn_counter": 3 
                            | "mode": "report_tag" 
                            | "mode": "init_player_tags"
                            
                        }
                    """
                    if is_raspberrypi() and self.__rfid_handler:
                        self.__rfid_handler.proc_rfid(params_json)
                case "timers":
                    """
                        /timer/ {"remaining": 120}
                        timer variables can be used on the LCD screen as 
                        ${variables} with a autoformat like mm:ss or hh:mm:ss 
                    """
                    if "_clearall" in params_json.keys():
                        # removes all timers
                        self.__my_context.clear_timers()
                    else:
                        for key, value in params_json.items():
                            try:
                                # make sure that strings and ints are accepted
                                # refuse otherwise
                                self.__my_context.set_timer(key, int(value))
                            except ValueError:
                                self.__my_context.log.warning(f"Invalid timer {value}")
                case "vars":
                    for key, value in params_json.items():
                        # variables are always strings
                        self.__my_context.variables[key] = str(value)
                case "reset_status":
                    self.__my_context.reset_stats()
                case "status":
                    self.__my_status_job.send_status(self.__my_context.get_current_wifi_signal_strength())
                case _:
                    self.__my_context.log.warning(f"got command '{cmd}' but don't know what to do with it")
        except Exception as ex:
            message = "An exception of type {0} occurred. Arguments:\n{1!r}".format(type(ex).__name__, ex.args)
            self.__my_context.log.warning(f"{message}")
            self.__my_context.log.warning("exception occurred while receiving an mqtt message. Ignoring it.")

    def __search_for_broker(self) -> str:
        self.__pre_init_page()
        trying_broker_with_index: int = 0
        mqtt_broker: str = ""
        while not self.__connected:
            # if the context has a broker already, then we must be reconnecting. No need to try out all brokers again
            mqtt_broker = self.__my_context.mqtt_broker if self.__my_context.mqtt_broker \
                else self.__my_context.configs["network"]["mqtt"]["broker"][trying_broker_with_index]

            self.__render_signal_quality(self.__my_context.get_current_wifi_signal_strength()[0])
            try:
                self.__my_context.log.info(f"trying broker: '{mqtt_broker}'")
                self.__my_context.variables["broker"] = mqtt_broker
                self.__mqtt_client.connect(mqtt_broker, port=self.__my_context.MQTT_PORT,
                                           keepalive=self.__my_context.configs["network"]["mqtt"]["keepalive"])
                self.__mqtt_client.loop_start()
                time.sleep(2)
            except OSError as os_ex:
                trying_broker_with_index += 1
                if trying_broker_with_index >= len(self.__my_context.configs["network"]["mqtt"]["broker"]):
                    trying_broker_with_index = 0
                self.__my_context.log.info(f"couldn't connect- retrying broker {os_ex}")
            except Exception as e:
                self.__my_context.log.error(f"search_for_broker exception{e}")

        self.__my_context.mqtt_broker = mqtt_broker

    def __render_signal_quality(self, signal_quality: int):
        """
        show current WI-FI signal strength on the led bar
        :param signal_quality: signal quality in percent
        :return: NOTHING
        """
        # shortcut
        if signal_quality == self.__prev_signal_quality:
            return
        self.__prev_signal_quality = signal_quality
        # render
        net_status: [str, str] = {"led_all": "off"}
        if signal_quality == 0:
            net_status["wht"] = "no_wifi"
        if signal_quality > 0:
            net_status["wht"] = "signal_strength"
        if signal_quality >= 20:
            net_status["red"] = "signal_strength"
        if signal_quality >= 40:
            net_status["ylw"] = "signal_strength"
        if signal_quality >= 60:
            net_status["grn"] = "signal_strength"
        if signal_quality >= 80:
            net_status["blu"] = "signal_strength"
        self.__my_pin_handler.proc_pins(net_status)
