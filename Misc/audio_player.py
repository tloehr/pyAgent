from context import Context
from subprocess import Popen
from os import sep, listdir, path
import random


class AudioPlayer:
    def __init__(self, my_context: Context):
        self.__process_map = {}
        self.__my_context = my_context

    def proc_play(self, incoming):
        self.__play(channel=incoming["channel"], sub_path=incoming["subpath"], song=incoming["soundfile"])

    def __play(self, channel: str, sub_path: str, song: str):
        if not self.__my_context.PLAYER_BIN:
            return
        if song == "<random>":
            song = self.__pick_random_file(sub_path)
        audiofile = self.__get_audio_file(sub_path, song)
        self.__stop(channel)
        if not song:
            return
        call_params: [str] = [self.__my_context.PLAYER_BIN]
        if self.__my_context.PLAYER_OPTS:
            call_params.append(self.__my_context.PLAYER_OPTS)
        call_params.append(audiofile)
        self.__process_map[channel] = Popen(call_params)

    def __stop(self, channel: str):
        if channel in self.__process_map:
            self.__process_map[channel].kill()

    def __pick_random_file(self, sub_path: str) -> str:
        list_of_files: [str] = []
        for file in listdir(self.__my_context.WORKSPACE + sep + "audio" + sep + sub_path):
            if file.endswith(".mp3"):
                list_of_files.append(file)
        return random.choice(list_of_files)

    def __get_audio_file(self, sub_path: str, song: str) -> str:
        audio_file: str = self.__my_context.WORKSPACE + sep + "audio" + sep + sub_path + sep + song
        if not path.exists(audio_file):
            audio_file = ""
        return audio_file
