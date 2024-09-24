from mafia_chatbot.game.player_info import *

class Strategy :
    def __init__(self, targets: list[PlayerInfo], reason: str = '', publicRole: Role = None) :
        self.targets = targets
        self.publicRole = publicRole

        self.mainTarget = self.targets[0]

        self.reason = reason
