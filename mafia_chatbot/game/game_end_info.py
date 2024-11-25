from enum import Enum

from mafia_chatbot.network.messages import *

class GameEndReason(Enum) :
    CITIZEN_WIN = 0
    MAFIA_WIN = 1
    NO_HUMAN_PLAYER = 2

gameEndReasonToProtoDict: dict[GameEndReason, game_pb2.GameEndReason] = {
    GameEndReason.CITIZEN_WIN: game_pb2.GameEndReason.GAME_END_CITIZEN_WIN,
    GameEndReason.MAFIA_WIN: game_pb2.GameEndReason.GAME_END_MAFIA_WIN,
    GameEndReason.NO_HUMAN_PLAYER: game_pb2.GameEndReason.GAME_END_NO_HUMAN_PLAYER,
}

class GameEndInfo :
    def __init__(self, reason: GameEndReason) :
        self.reason = reason
