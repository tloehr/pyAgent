import threading
import sys
import time
import json
from pathlib import PurePath, Path
from PinHandler.my_pin import MyPin
from PinHandler.pin_scheme import PinScheme
from context import Context
from os import path

PERIOD = 25  # ms
SLEEP = PERIOD / 1000
ALL_SIRENS = ["sir1", "sir2", "sir3", "sir4", "buzzer"]
ALL_LEDS = ["wht", "red", "ylw", "grn", "blu"]


class PinHandler(threading.Thread):
    def __init__(self, my_context: Context):
        self.SCHEME_MACROS: json = None
        self.__lock = threading.Lock()
        self.__pin_registry: [str, MyPin] = {}
        threading.Thread.__init__(self)
        self.__my_context = my_context

        macros: str = path.abspath(path.join(path.dirname(__file__), "scheme_macros.json"))
        with open(macros) as my_macros:
            self.SCHEME_MACROS = json.loads(my_macros.read())

        # macros: Path
        # if Path("/opt/pyAgent/scheme_macros.json").exists():
        #     macros = Path("/opt/pyAgent/scheme_macros.json")
        # else:
        #     macros = Path(self.__my_context.WORKSPACE, "scheme_macros.json")
        # with open(macros) as my_file:
        #     self.SCHEME_MACROS = json.loads(my_file.read())

        self.__add("wht")
        self.__add("red")
        self.__add("ylw")
        self.__add("grn")
        self.__add("blu")
        self.__add("buzzer")
        self.__add("sir1")
        self.__add("sir2")
        self.__add("sir3")
        self.__add("sir4")
        self.start()

    def run(self):
        self.__my_context.log.debug("PinHandler Loop starting... ")
        while True:
            self.__lock.acquire()
            for key, my_pin_scheme in self.__pin_registry.items():
                my_pin_scheme.next()
            self.__lock.release()
            time.sleep(SLEEP)

    def __add(self, mypin_name: str):
        self.__my_context.log.debug(f"adding pin {mypin_name}")
        self.__pin_registry[mypin_name] = PinScheme(mypin_name, self.__my_context)

    def leds_off(self):
        for pin in ALL_LEDS:
            self.off(pin)

    def sirens_off(self):
        for pin in ALL_SIRENS:
            self.off(pin)

    def off(self, pin):
        self.__pin_registry[pin].clear()

    def proc_pins(self, incoming: json):
        self.__lock.acquire()
        self.__my_context.log.debug(f"incoming json{json.dumps(incoming)}")
        # Preprocess sir_all and led_all device selectors
        # off is processed first, and then removed from the message
        # other schemes are duplicated to their devices names.
        if "sir_all" in incoming:
            if str(incoming["sir_all"]).lower() == "off":
                for pin in ALL_SIRENS:
                    self.off(pin)
            else:
                for pin in ALL_SIRENS:
                    incoming[pin] = incoming["sir_all"]
            del incoming["sir_all"]
        #
        if "led_all" in incoming:
            if str(incoming["led_all"]).lower() == "off":
                for pin in ALL_LEDS:
                    self.off(pin)
            else:
                for pin in ALL_LEDS:
                    incoming[pin] = incoming["led_all"]
            del incoming["led_all"]
        #
        for key, value in incoming.items():
            self.__my_context.log.debug(f"found key: {key}")
            if str(value).lower() == "off":
                self.off(key)
                return
            if str(value).lower() in self.SCHEME_MACROS:
                json_scheme = self.SCHEME_MACROS[value]
            else:
                json_scheme = value
            repeat = sys.maxsize if json_scheme["repeat"] < 0 else json_scheme["repeat"] - 1
            self.__pin_registry[key].init(repeat, json_scheme["scheme"])
        #
        self.__lock.release()
