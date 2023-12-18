ROWS: int = 4


class LCDPage:

    def __init__(self, name):
        self.__lines = []
        self.__name = name
        self.clear()

    def clear(self):
        self.__lines.clear()
        for row in range(ROWS):
            self.__lines.append("")

    def set_line(self, num, text):
        self.__lines[num] = text

    def get_line(self, num):
        return self.__lines[num]

    def get_name(self):
        return self.__name
