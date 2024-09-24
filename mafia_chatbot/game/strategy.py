from mafia_chatbot.game.player_info import *

class Strategy :
    def __init__(self, assumptions: list[tuple[PlayerInfo, Role]], publicRole: Role = None, reason: str = '') :
        self.assumptions = assumptions
        self.publicRole = publicRole
        self.reason = reason

        self.mainTarget: PlayerInfo = None
        for player, role in assumptions :
            if role == Role.MAFIA :
                self.mainTarget = player
                break

    def getDescription(self) :
        return f'publicRole={self.publicRole}, assumptions={self.assumptions}, prompt={self.reason}'
