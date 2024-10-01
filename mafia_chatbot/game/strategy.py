from mafia_chatbot.game.player_info import *

class Assumption :
    def __init__(self,
            roleEstimates: list[tuple[PlayerInfo, Role]],
            reason: str,
            isFirst: bool = False,
            isSurelyMafia: bool = False) :

        self.roleEstimates = roleEstimates
        self.reason = reason

        self.isFirst = isFirst
        self.isSurelyMafia = isSurelyMafia

    def __str__(self) :
        estimates = ','.join(map(lambda estimate: f'{estimate[0].name}={estimate[1].name.lower()}', self.roleEstimates))
        return f'{estimates} ({self.reason})'

    def __repr__(self) :
        return self.__str__()

    def getPrompt(self) :
        estimates = ', '.join(map(lambda estimate: f'{estimate[0].name}\'s role is {estimate[1].name.lower()}', self.roleEstimates)) 
        return f'{estimates} because {self.reason}.'

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
        return '\n'.join(map(lambda assumption: assumption.getPrompt(), self.assumptions))
