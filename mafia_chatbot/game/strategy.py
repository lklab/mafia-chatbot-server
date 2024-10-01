from mafia_chatbot.game.player_info import *

class Estimate :
    def __init__(self,
            playerInfo: PlayerInfo,
            role: Role,
            isFirst: bool = False,
            isSurelyMafia: bool = False) :

        self.playerInfo = playerInfo
        self.role = role
        self.isFirst = isFirst
        self.isSurelyMafia = isSurelyMafia

    def __str__(self) :
        return f'{self.playerInfo.name}={self.role.name.lower()}'

    def __repr__(self) :
        return self.__str__()

    def getPrompt(self) :
        return f'{self.playerInfo.name}\'s role is {self.role.name.lower()}'

class Assumption :
    def __init__(self, estimates: list[Estimate], reason: str) :
        self.estimates = estimates
        self.reason = reason

    def __str__(self) :
        estimates = ','.join(map(lambda estimate: str(estimate), self.estimates))
        return f'{estimates} ({self.reason})'

    def __repr__(self) :
        return self.__str__()

    def getPrompt(self) :
        estimates = ', '.join(map(lambda estimate: estimate.getPrompt(), self.estimates)) 
        return f'{estimates} because {self.reason}.'

class Strategy :
    def __init__(self, publicRole: Role, assumptions: list[Assumption]) :
        self.publicRole = publicRole
        self.assumptions = assumptions

        self.mainMafiaAssumption : Assumption = None
        self.mainTarget: PlayerInfo = None

        for assumption in assumptions :
            for estimate in assumption.estimates :
                if estimate.role == Role.MAFIA :
                    self.mainMafiaAssumption = assumption
                    self.mainTarget = estimate.playerInfo
                    break

    def __str__(self) :
        return f'publicRole={self.publicRole}, assumptions={self.assumptions}'

    def assumptionsToStr(self) :
        return str(self.assumptions)

    def assumptionsToPrompt(self) :
        return '\n'.join(map(lambda assumption: assumption.getPrompt(), self.assumptions))
