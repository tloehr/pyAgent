import threading
import time
from datetime import datetime, timedelta
from collections import OrderedDict
from PagedDisplay import lcd_page
from context import Context, is_raspberrypi

if is_raspberrypi():
    from RPLCD.i2c import CharLCD

ROWS: int = 4
COLS: int = 20
SECONDS_PER_CYCLE: float = 0.5
CYCLES_PER_PAGE: int = 2

AGVERSION: str = "1.0"
AGBDATE: str = "2023-12-19"
AGBUILD: str = "5"


class MyLCD(threading.Thread):

    def __init__(self, my_context: Context):
        threading.Thread.__init__(self)
        self.__use_lcd: bool = False
        """
            timers section
            it may seem odd, but for the agent all timers are just
            something that will show up on the display
            so we maintain them here
        """
        self.__timer_listeners = []
        self.__timers = {}
        self.__variables = {}
        self.__pages = OrderedDict()
        self.__page_index: int = 0
        self.__time_difference_since_last_cycle = 0
        self.__last_cycle_started_at = 0
        self.__lock = threading.Lock()
        self.__my_context = my_context
        if is_raspberrypi():
            try:
                self.__char_lcd = CharLCD('PCF8574',
                                          int(self.__my_context.configs["hardware"]["lcd"]["PCF8574"], 16)
                                          )
                self.__use_lcd = True
            except Exception as ex:
                self.__my_context.log.error(f"LCD display couldn't be initialized: {ex}")
                pass
        self.__init_class()
        self.start()

    # https://www.educba.com/python-event-handler/
    def __iadd__(self, e_handler):
        self.__timer_listeners.append(e_handler)
        return self

    def __isub__(self, e_handler):
        self.__timer_listeners.remove(e_handler)
        return self

    def __notify_listeners(self, key_name=None, old_value=None, new_value=None):
        for listener in self.__timer_listeners:
            listener(key_name=key_name, old_value=old_value, new_value=new_value)

    def __init_class(self):
        self.__loop_counter = 0
        self.__pages.clear()
        if self.__use_lcd:
            self.__char_lcd.clear()
        self.__pages["page0"] = lcd_page.LCDPage("page0")
        self.__variables["wifi"] = "--"
        self.__variables["ssid"] = "--"
        self.__variables["agversion"] = AGVERSION
        self.__variables["agbuild"] = AGBUILD
        self.__variables["agbdate"] = AGBDATE
        self.__variables["agentname"] = self.__my_context.MY_ID
        self.__set_line("page0", 1, "pyAgent ${agversion}b${agbuild}")
        self.__set_line("page0", 2, "")
        self.__set_line("page0", 3, "")
        self.__set_line("page0", 4, "Initializing...")

    def run(self):
        self.__my_context.log.trace("LCD Loop starting... ")
        while True:
            self.__lock.acquire()
            self.__calculate_timers()
            if self.__loop_counter % CYCLES_PER_PAGE == 0:
                self.__next_page()  # if necessary
                self.__display_active_page()
            self.__lock.release()
            time.sleep(SECONDS_PER_CYCLE)
            self.__loop_counter += 1

    def proc_paged(self, json):
        self.__lock.acquire()
        self.__init_class()
        for page, lines in json.items():
            self.__my_context.log.debug(f"paged: {page}, {lines}")
            num = 1
            for line in lines:
                self.__set_line(page, num, line)
                num += 1
        self.__lock.release()

    def __add_page(self, key: str):
        if key in self.__pages:
            self.__my_context.log.debug(f"re-using {key}")
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
                line = self.__replace_variables(line)[:COLS]
            line = line.ljust(COLS, " ")
            if self.__use_lcd:
                self.__char_lcd.cursor_pos = (row, 0)
                self.__char_lcd.write_string(line)
            # write to some device
            # prevent unnecessary refreshes
            #
            self.__my_context.log.trace(f"VISIBLE PAGE #{self.__page_index} Line {row}: '{line}'")

    def __calculate_timers(self):
        now = time.time_ns() / 1000000
        self.__time_difference_since_last_cycle = now - self.__last_cycle_started_at
        self.__last_cycle_started_at = now
        # fix variables for empty timers
        # and notify listeners if necessary
        for key, value in self.__timers.items():
            if value[1] - self.__time_difference_since_last_cycle < 0:
                self.__variables[key] = "--"
                self.__notify_listeners(key_name=key, old_value=value[0], new_value=0)

        # remove all timers that are zero and below
        # OR keep all the others to be precise
        # that's the reason for the >=0 in the comprehension
        self.__timers = {
            k: v for k, v in self.__timers.items()
            if v[1] - self.__time_difference_since_last_cycle >= 0
        }
        # recalculate all timers
        self.__timers = {
            k: [v[0], v[1] - self.__time_difference_since_last_cycle]
            for k, v in self.__timers.items()
        }
        # re-set all variables
        for key, value in self.__timers.items():
            self.__my_context.log.trace(f"time {key} is now {value[1]}")
            pattern = "%M:%S" if value[1] < 3600000 else "%H:%M:%S"
            new_time_value = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                milliseconds=value[1])
            self.set_variable(key, new_time_value.strftime(pattern))
            # this event will be sent out to realize a Progress Bar via the LEDs.
            self.__notify_listeners(key_name=key, old_value=value[0], new_value=value[1])

    def set_variable(self, key: str, var: str):
        self.__my_context.log.trace(f"setting variable {key} to {var}")
        self.__variables[key] = var

    def set_timer(self, key: str, time_in_secs: int):
        self.__my_context.log.trace(f"setting timer {key} to {time_in_secs}")
        # we have to add one second here so the display fits to the timer notion of the players.
        initial_value = (time_in_secs + 1) * 1000
        # left Long = starting value -> never changes
        # right Long = decreasing value ends with 0
        self.__timers[key] = [initial_value, initial_value]

    def clear_timers(self):
        for key in self.__timers.keys():
            self.__variables[key] = "--"
        self.__timers.clear()

    def __replace_variables(self, line: str) -> str:
        text = line
        for key, value in self.__variables.items():
            # log.debug(f"before {text}")
            # log.debug(f"replacing ${{{key}}} with {value}")
            text = text.replace(f"${{{key}}}", str(value))
        # log.debug(f"after {text}")
        return text
