from mafia_chatbot.game.player_info import *

class Estimation :
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
    def __init__(self, estimations: list[Estimation], reason: str) :
        self.estimations = estimations
        self.reason = reason

    def __str__(self) :
        estimations = ','.join(map(lambda estimation: str(estimation), self.estimations))
        return f'{estimations} ({self.reason})'

    def __repr__(self) :
        return self.__str__()

    def getPrompt(self) :
        estimations = ', '.join(map(lambda estimation: estimation.getPrompt(), self.estimations)) 
        return f'{estimations} because {self.reason}.'

class Strategy :
    def __init__(self, publicRole: Role, assumptions: list[Assumption]) :
        self.publicRole = publicRole
        self.assumptions = assumptions

        self.mainMafiaAssumption : Assumption = None
        self.mainTarget: PlayerInfo = None

        for assumption in assumptions :
            for estimation in assumption.estimations :
                if estimation.role == Role.MAFIA :
                    self.mainMafiaAssumption = assumption
                    self.mainTarget = estimation.playerInfo
                    break
            if self.mainMafiaAssumption == None :
                break

        self.estimations: list[Estimation] = [estimation for assumption in assumptions for estimation in assumption.estimations]

    def __str__(self) :
        return f'publicRole={self.publicRole.name.lower()}, assumptions={self.assumptions}'

    def assumptionsToStr(self) :
        return str(self.assumptions)

    def assumptionsToPrompt(self) :
        return '\n'.join(map(lambda assumption: assumption.getPrompt(), self.assumptions))

class VoteStrategy(Strategy) :
    def __init__(self, estimation: Estimation) :
        assumption = Assumption([estimation], '')
        super().__init__(
            publicRole=Role.CITIZEN, # not used
            assumptions=[assumption],
        )
