import logging
import datetime
import os

from mafia_chatbot.game.player import Player
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

    def logCandidatesPlayer(self, players: list[Player]) :
        self.log(f'candidates: {', '.join(map(lambda p : p.info.name, players))}')

    def logCandidatesWithWeights(self, playerInfos: list[PlayerInfo], weights: list[float]) :
        total: float = sum(weights)
        self.log(f'candidates: {', '.join(map(lambda i : f'{playerInfos[i].name}({weights[i] * 100.0 / total:.2f})', range(len(playerInfos))))}')

    def logCandidatesPlayerWithWeights(self, players: list[Player], weights: list[float]) :
        total: float = sum(weights)
        self.log(f'candidates: {', '.join(map(lambda i : f'{players[i].info.name}({weights[i] * 100.0 / total:.2f})', range(len(players))))}')

class FakeGameLogger :
    def log(self, message: str) :
        pass
    def logCandidates(self, playerInfos: list[PlayerInfo]) :
        pass
    def logCandidatesPlayer(self, player: list[Player]) :
        pass
    def logCandidatesWithWeights(self, playerInfos: list[PlayerInfo], weights: list[float]) :
        pass
    def logCandidatesPlayerWithWeights(self, players: list[Player], weights: list[float]) :
        pass
