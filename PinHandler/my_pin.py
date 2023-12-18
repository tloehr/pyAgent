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

        self.__my_context = my_context
        self.__prev_value = -1
        self.name: str = name
        gpio: str = self.__my_context.configs["hardware"][self.name]
        self.__my_context.log.trace(f"trying {name} at hw pin {gpio}")
        self.__pin: LED = LED(gpio)
        self.__pin.value = 0

    def set_value(self, state: int):
        self.__pin.value = state
        if state != self.__prev_value:
            self.__prev_value = state
            self.__my_context.log.trace(f"pin_state '{self.name}' is {self.__pin.value}")

    def __str__(self) -> str:
        return f"{self.name}: {self.__pin.value}"
