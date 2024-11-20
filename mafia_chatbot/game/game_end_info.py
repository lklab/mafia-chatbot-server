from enum import Enum

class GameEndReason(Enum) :
    CITIZEN_WIN = 0
    MAFIA_WIN = 1
    NO_HUMAN_PLAYER = 2

class GameEndInfo :
    def __init__(self, reason: GameEndReason) :
        self.reason = reason
