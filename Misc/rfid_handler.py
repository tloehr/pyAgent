from context import Context
import binascii
import json
import time
from threading import Thread
from pn532pi import Pn532, pn532
from pn532pi import Pn532I2c
import paho.mqtt.client as mqtt

MQTT_REPORT_EVENT: str = "/rfid"
KEY_DEFAULT_KEYAB = bytearray([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
RECORD_TYPE_REVIVE_COUNTER: int = 1
STARTING_BLOCK_NUMBER: int = 4

HANDLER_MODE_REVIVAL: int = 0
"""
agent is in MEDIC mode. respawn counter on cards are decreased. denied when counter is zero.
"""
HANDLER_MODE_RESET_LIVES: int = 1
"""
agent is in RESPAWN mode. cards are reset to the max number of lives
"""
HANDLER_MODE_REPORT_UID: int = 2
"""
agent simply reports the card's uid via MQTT. THIS IS THE DEFAULT.
"""


class _RFIDException(Exception):
    """something is wrong with the rfid process"""
    pass


class RfidHandler(Thread):

    def __init__(self, mqtt_client: mqtt.Client, my_context: Context):
        self.__my_context: Context = my_context
        self.__mqtt_client: mqtt.Client = mqtt_client

        Thread.__init__(self)

        # inactive when no rfid is set in the configs
        self.__active: bool = self.__my_context.configs["hardware"]["rfid"]
        if not self.__active:
            return

        # default is the report uid mode
        self.__mode: int = HANDLER_MODE_REPORT_UID

        self.__nfc = Pn532(Pn532I2c(self.__my_context.configs["hardware"]["rfid"]["pn532_i2c_bus"]))
        self.__nfc.begin()

        version_data: int = self.__nfc.getFirmwareVersion()
        if not version_data:
            self.__active = False
            self.__my_context.log.warning("Didn't find a PN53x board")
            return

        self.__my_context.log.debug(
            f"Found chip PN5 {(version_data >> 24) & 0xFF} Firmware ver. {(version_data >> 16) & 0xFF}.{(version_data >> 8) & 0xFF}"
        )
        # Configures the SAM (Secure Access Module)
        self.__nfc.SAMConfig()
        # start the thread
        self.start()

    def __authenticate(self, uid: bytearray, starting_block: int, number_of_blocks: int):
        all_authenticated: bool = True
        # checking all blocks for authentication
        block: int = starting_block
        while block < starting_block + number_of_blocks:
            all_authenticated = all_authenticated and self.__nfc.mifareclassic_AuthenticateBlock(uid,
                                                                                                 block, 0,
                                                                                                 KEY_DEFAULT_KEYAB)
            block = self.__next_block_number_mifare_card(block)

        if not all_authenticated:
            raise _RFIDException("card authentication failed")

    def __write_to_card(self, uid: bytearray, starting_block: int, payload: [int]):
        self.__authenticate(uid, starting_block, len(payload))
        block: int = starting_block
        for value in payload:
            content: bytearray = bytearray(value.to_bytes(16, "big"))
            self.__nfc.mifareclassic_WriteDataBlock(block, content)
            block = self.__next_block_number_mifare_card(block)

    def __next_block_number_mifare_card(self, block: int) -> int:
        # if the next block(+1) is multitude of 4 then it is a protected sector trailer
        # and needs to be skipped
        block += 1
        if block + 1 % 4 == 0:
            block += 1
        return block

    def __read_from_card(self, uid: bytearray, starting_block: int, number_of_blocks: int) -> [int]:
        self.__authenticate(uid, starting_block, number_of_blocks)
        payload: [int] = []
        block: int = starting_block
        while block < starting_block + number_of_blocks:
            (success, block_buffer) = self.__nfc.mifareclassic_ReadDataBlock(block)
            payload.append(int.from_bytes(block_buffer, "big"))
            block = self.__next_block_number_mifare_card(block)

    def run(self):
        # loop only runs, when the card reader is working and active
        while self.__active:
            try:
                card_detected, uid = self.__nfc.readPassiveTargetID(
                    cardbaudrate=pn532.PN532_MIFARE_ISO14443A_106KBPS)
                if len(uid) != 4:
                    raise _RFIDException("this doesn't seem to be a Mifare Classic card")

                if self.__mode == HANDLER_MODE_REPORT_UID:
                    self.__report_uid(uid)
                elif self.__mode == HANDLER_MODE_REVIVAL:
                    self.__revive_player(uid)
                elif self.__mode == HANDLER_MODE_RESET_LIVES:
                    self.__reset_lives(uid)

            except _RFIDException as exc:
                self.__my_context.log.warning(exc)
            time.sleep(1)

    def __report_uid(self, uid):
        self.__my_context.log.debug(f"reporting Card-UID: {binascii.hexlify(uid)}")
        self.__report_event({"rfid": uid})
        pass

    def __report_event(self, event: {}):
        if not self.__mqtt_client.is_connected():
            return
        self.__mqtt_client.publish(self.__my_context.MQTT_OUTBOUND + MQTT_REPORT_EVENT, json.dumps(event),
                                   self.__my_context.MQTT_RFID_QOS, True)

    def __revive_player(self, uid):
        record_type, revive_counter, revive_max = self.__read_from_card(uid, STARTING_BLOCK_NUMBER, 3)
        if record_type != RECORD_TYPE_REVIVE_COUNTER:
            raise _RFIDException("no revive record - ignoring")

        if revive_counter <= 0:
            self.__my_context.log.info("no more lives - go back to the spawn")
        else:
            self.__my_context.log.info(f"player {uid} has {revive_counter - 1} lives left")
            self.__write_to_card(uid, STARTING_BLOCK_NUMBER + 1, [revive_counter - 1])

    def __reset_lives(self, uid):
        record_type, revive_counter, revive_max = self.__read_from_card(uid, STARTING_BLOCK_NUMBER, 3)
        if record_type != RECORD_TYPE_REVIVE_COUNTER:
            raise _RFIDException("no revive record - ignoring")
        self.__write_to_card(uid, STARTING_BLOCK_NUMBER + 1, [revive_max])

    def proc_rfid(self, incoming: json):
        if not self.__active:
            return
        self.__my_context.log.debug(incoming)
        match incoming["mode"]:
            case "revive_player":
                self.__mode = HANDLER_MODE_REVIVAL
            case "report_uid":
                self.__mode = HANDLER_MODE_REPORT_UID
            case "reset_lives":
                self.__mode = HANDLER_MODE_RESET_LIVES
            case _:
                self.__my_context.log.warning("unknown rfid command")
