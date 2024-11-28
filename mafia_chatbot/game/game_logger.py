import logging
import datetime
import os

from mafia_chatbot.game.player_info import PlayerInfo

class GameLogger :
    def __init__(self, gameId: str, path: str) :
        time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.name = f'[{time}]_eval_{gameId}'
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)

        file_handler = logging.FileHandler(os.path.join(path, f'{self.name}.log'), encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(message)s')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        self.logger = logger

    def log(self, message: str) :
        self.logger.debug(message)

    def logCandidates(self, playerInfos: list[PlayerInfo]) :
        self.log(f'candidates: {', '.join(map(lambda info : info.name, playerInfos))}')

class FakeGameLogger :
    def log(self, message: str) :
        pass
    def logCandidates(self, playerInfos: list[PlayerInfo]) :
        pass
