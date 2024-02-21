from threading import Thread, Lock
import time
from collections import OrderedDict
from PagedDisplay import lcd_page
from context import Context, is_raspberrypi

if is_raspberrypi():
    from RPLCD.i2c import CharLCD

ROWS: int = 4
COLS: int = 20
SECONDS_PER_CYCLE: float = 0.5
CYCLES_PER_PAGE: int = 4

# https://rplcd.readthedocs.io/en/stable/usage.html#creating-custom-characters
LCD_ANTENNA = (
    0b11111,
    0b10001,
    0b01010,
    0b00100,
    0b00100,
    0b00100,
    0b00100,
    0b00000
)

WIFI_POOR = (
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b10000,
    0b00000
)

WIFI_FAIR = (
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b01000,
    0b11000,
    0b00000
)

WIFI_GOOD = (
    0b00000,
    0b00000,
    0b00000,
    0b00000,
    0b00100,
    0b01100,
    0b11100,
    0b00000
)

WIFI_VERY_GOOD = (
    0b00000,
    0b00000,
    0b00000,
    0b00010,
    0b00110,
    0b01110,
    0b11110,
    0b00000
)

WIFI_PERFECT = (
    0b00000,
    0b00000,
    0b00001,
    0b00011,
    0b00111,
    0b01111,
    0b11111,
    0b00000
)


class MyLCD(Thread):

    def __init__(self, my_context: Context):
        Thread.__init__(self)
        self.__use_lcd: bool = False
        self.__pages = OrderedDict()
        self.__page_index: int = 0
        self.__last_cycle_started_at: float = 0
        self.__lock = Lock()
        self.__my_context = my_context
        self.__my_context.set_wifi_vars(signal_quality=0)

        if is_raspberrypi():
            try:
                self.__char_lcd = CharLCD(self.__my_context.configs["hardware"]["lcd"]["i2c_expander"],
                                          int(self.__my_context.configs["hardware"]["lcd"]["address"], 16)
                                          )
                self.__use_lcd = True
                self.__init_custom_wifi_chars()
            except Exception as ex:
                self.__my_context.log.error(f"LCD display couldn't be initialized: {ex}")
                self.__use_lcd = False

        self.__init_class()
        self.start()

    def __init_custom_wifi_chars(self):
        """
        creating 5 chars to show the wi-fi signal strength in a common fashion
        creating 1 Antenna Symbol
        :return:
        """
        self.__char_lcd.create_char(0, LCD_ANTENNA)
        self.__char_lcd.create_char(1, WIFI_POOR)
        self.__char_lcd.create_char(2, WIFI_FAIR)
        self.__char_lcd.create_char(3, WIFI_GOOD)
        self.__char_lcd.create_char(4, WIFI_VERY_GOOD)
        self.__char_lcd.create_char(5, WIFI_PERFECT)

    def __init_class(self):
        self.__loop_counter = 0
        self.__pages.clear()
        self.__page_index = 0
        if self.__use_lcd:
            self.__char_lcd.clear()
        self.__pages["page0"] = lcd_page.LCDPage("page0")
        self.__my_context.variables["ssid"] = "--"
        self.__set_line("page0", 1, "pyAgent ${agversion}b${agbuild}")
        self.__set_line("page0", 2, "")
        self.__set_line("page0", 3, "")
        self.__set_line("page0", 4, "Initializing...   ${wifi_signal}")

    def run(self):
        self.__my_context.log.trace("LCD Loop starting... ")
        while True:
            self.__lock.acquire()
            now: float = time.time_ns() / 1000000
            self.__my_context.calculate_timers(self.__last_cycle_started_at, now)
            self.__last_cycle_started_at = now
            if self.__loop_counter % CYCLES_PER_PAGE == 0:
                self.__next_page()  # if necessary
            self.__display_active_page()
            self.__lock.release()
            time.sleep(SECONDS_PER_CYCLE)
            self.__loop_counter += 1

    def proc_paged(self, json):
        self.__lock.acquire()
        try:
            self.__init_class()
            for page, lines in json.items():
                self.__my_context.log.debug(f"paged: {page}, {lines}")
                num = 1
                for line in lines:
                    self.__set_line(page, num, line)
                    num += 1
        except Exception as ex:
            self.__my_context.log.error(f"error parsing scheme: {ex}")
        finally:
            self.__lock.release()

    def __add_page(self, key: str):
        if key in self.__pages:
            return
        self.__my_context.log.debug(f"adding page {key}")
        self.__pages[key] = lcd_page.LCDPage(key)

    def __set_line(self, key: str, line: int, text: str):
        self.__add_page(key)
        if line < 1 or line > ROWS:
            return
        self.__pages[key].set_line(line - 1, text)

    def __next_page(self):
        self.__my_context.log.trace(f"pages size {len(self.__pages)}")
        if len(self.__pages) == 1:
            return
        self.__page_index += 1
        if self.__page_index >= len(self.__pages):
            self.__page_index = 0
        self.__my_context.log.trace(f"index of active_page {self.__page_index}")

    def __display_active_page(self):
        active_page_key: str = list(self.__pages.keys())[self.__page_index]
        for row in range(ROWS):
            line = self.__pages[active_page_key].get_line(row)
            if line:
                line = self.__my_context.replace_variables(line)[:COLS]
            line = line.ljust(COLS, " ")
            if self.__use_lcd:
                self.__char_lcd.cursor_pos = (row, 0)
                self.__char_lcd.write_string(line)
            # write to some device
            # prevent unnecessary refreshes
            #
            self.__my_context.log.trace(f"VISIBLE PAGE #{self.__page_index} Line {row}: '{line}'")
