from PinHandler import pin_handler
from PinHandler.my_pin import MyPin
from context import Context


class PinScheme:

    def __init__(self, mypin_name: str, my_context: Context):
        self.__scheme: list[int] = []
        self.__pointer: int = 0
        self.__repeat: int = 0
        self.__my_pin: MyPin
        self.__my_context: Context = my_context
        self.__my_pin = MyPin(mypin_name, self.__my_context)

    def clear(self):
        self.__my_context.log.trace(f"clearing scheme for pin '{self.__my_pin.name}'")
        self.__scheme.clear()
        self.__repeat = 0
        self.__pointer = 0
        self.__my_pin.set_value(0)

    def init(self, repeat, json_scheme):
        self.clear()
        self.__repeat = repeat
        for value in json_scheme:
            multiplier = abs(int(value) // pin_handler.PERIOD)
            sign = 1 if value >= 0 else -1
            #
            for i in range(multiplier):
                self.__scheme.append(pin_handler.PERIOD * sign)

    def next(self):
        if not self.__scheme:
            return
        #
        self.__my_context.log.trace(
            f"{self.__my_pin.name}: pointer: {self.__pointer} = {self.__scheme[self.__pointer]}")
        self.__my_pin.set_value(1 if self.__scheme[self.__pointer] >= 0 else 0)
        self.__pointer += 1
        if self.__pointer >= len(self.__scheme):
            self.__pointer = 0
            if self.__repeat:
                self.__my_context.log.trace(f"reached end of scheme list - repeat #{self.__repeat} ")
                self.__repeat -= 1
            else:
                self.__my_context.log.trace(f"reached end of scheme list - no more repeats - done")
                self.clear()
