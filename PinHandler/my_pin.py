from context import is_raspberrypi, Context
from gpiozero import Device, LED

if is_raspberrypi():
    from gpiozero.pins.rpigpio import RPiGPIOFactory
else:
    from gpiozero.pins.mock import MockFactory


class MyPin:
    def __init__(self, name: str, my_context: Context):
        if is_raspberrypi():
            Device.pin_factory = RPiGPIOFactory()
        else:
            Device.pin_factory = MockFactory()
        self.name: str = name
        self.__my_context = my_context
        self.__INVERTED_TRIGGER = self.name in self.__my_context.LOW_TRIGGER
        self.__prev_value = -1
        gpio: str = self.__my_context.configs["hardware"][self.name]
        self.__my_context.log.trace(f"trying {name} at hw pin {gpio}")
        self.__pin: LED = LED(gpio)
        self.__pin.value = self.__correct_value(0)

    def set_value(self, value: int):
        self.__pin.value = self.__correct_value(value)
        if value != self.__prev_value:
            self.__prev_value = value
            self.__my_context.log.trace(f"pin_state '{self.name}' is {self.__pin.value}")

    def __str__(self) -> str:
        return f"{self.name}: {self.__correct_value(self.__pin.value)}"

    def __correct_value(self, value: int) -> int:
        """
        inverts the value if pin is in the LOW_TRIGGER list (necessary for sirens)
        :param value: the wanted value in the default notion of (1 is on, 0 is off)
        :return: corrected value if this pin is in the inversion list (config.json)
        """
        return 1 - value if self.__INVERTED_TRIGGER else value
