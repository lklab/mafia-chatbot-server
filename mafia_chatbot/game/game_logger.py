import logging
import datetime
import os
from enum import Enum
import traceback

from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo

class TAG(Enum) :
    INFO = 0
    CHAT = 1
    PHASE = 2
    DISCUSSION = 3
    STRATEGY = 4
    TRUST = 5
    LLM = 6
    NETWORK = 7
    ERROR = 99

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

    def log(self, tag: TAG, message: str) :
        self.logger.debug(f'[{tag.name}] {message}')

    def logError(self, message: str, e: Exception) :
        self.logger.error(f'[EXCEPTION] {message}: {e}')
        self.logger.error(traceback.format_exc())

    def logCandidates(self, tag: TAG, playerInfos: list[PlayerInfo]) :
        self.logger.debug(f'[{tag.name}] candidates: {', '.join(map(lambda info : info.name, playerInfos))}')

    def logCandidatesPlayer(self, tag: TAG, players: list[Player]) :
        self.logger.debug(f'[{tag.name}] candidates: {', '.join(map(lambda p : p.info.name, players))}')

    def logCandidatesWithWeights(self, tag: TAG, playerInfos: list[PlayerInfo], weights: list[float]) :
        total: float = sum(weights)
        self.logger.debug(f'[{tag.name}] candidates: {', '.join(map(lambda i : f'{playerInfos[i].name}({weights[i] * 100.0 / total:.2f})', range(len(playerInfos))))}')

    def logCandidatesPlayerWithWeights(self, tag: TAG, players: list[Player], weights: list[float]) :
        total: float = sum(weights)
        self.logger.debug(f'[{tag.name}] candidates: {', '.join(map(lambda i : f'{players[i].info.name}({weights[i] * 100.0 / total:.2f})', range(len(players))))}')

class FakeGameLogger :
    def log(self, tag: TAG, message: str) :
        pass
    def logCandidates(self, tag: TAG, playerInfos: list[PlayerInfo]) :
        pass
    def logCandidatesPlayer(self, tag: TAG, player: list[Player]) :
        pass
    def logCandidatesWithWeights(self, tag: TAG, playerInfos: list[PlayerInfo], weights: list[float]) :
        pass
    def logCandidatesPlayerWithWeights(self, tag: TAG, players: list[Player], weights: list[float]) :
        pass
