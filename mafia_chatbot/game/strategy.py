from mafia_chatbot.game.player_info import *

class Assumption :
    def __init__(self,
            playerInfo: PlayerInfo,
            role: Role,
            reason: str,
            isFirst: bool = False,
            isSurelyMafia: bool = False) :

        self.playerInfo = playerInfo
        self.role = role
        self.reason = reason

        self.isFirst = isFirst
        self.isSurelyMafia = isSurelyMafia

    def __str__(self) :
        return f'{self.playerInfo.name}: {self.role.name.lower()} ({self.reason})'

    def __repr__(self) :
        return self.__str__()

    def getPrompt(self) :
        return f'the role of {self.playerInfo.name} is {self.role.name.lower()} because {self.reason}'

class Strategy :
    def __init__(self, publicRole: Role, assumptions: list[Assumption]) :
        self.publicRole = publicRole
        self.assumptions = assumptions

        self.mainMafiaAssumption : Assumption = None
        self.mainTarget: PlayerInfo = None

        for assumption in assumptions :
            if assumption.role == Role.MAFIA :
                self.mainMafiaAssumption = assumption
                self.mainTarget = assumption.playerInfo
                break

    def __str__(self) :
        return f'publicRole={self.publicRole}, assumptions={self.assumptions}'

    def assumptionsToStr(self) :
        return ', '.join(map(lambda assumption: str(assumption), self.assumptions))

    def assumptionsToPrompt(self) :
        return ', '.join(map(lambda assumption: assumption.getPrompt(), self.assumptions))
