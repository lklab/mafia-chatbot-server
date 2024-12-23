from enum import Enum

from mafia_chatbot.game.player_info import *

defaultReason = 'Due to a lack of information, you will suspect someone as the mafia, but it is only a guess. You might come up with a funny reason, or perhaps base your suspicion on something completely random like their tone of voice or the way they blinked.'

class Estimation :
    def __init__(self,
            playerInfo: PlayerInfo,
            role: Role) :

        self.playerInfo = playerInfo
        self.role = role

    def __str__(self) :
        return f'{self.playerInfo.name}={self.role.name.lower()}'

    def __repr__(self) :
        return self.__str__()

    def __eq__(self, other) :
        if isinstance(other, Estimation) :
            return self.playerInfo.id == other.playerInfo.id and self.role == other.role
        return False

    def __hash__(self):
        return hash((self.playerInfo.id, self.role))
 
    def getPrompt(self) :
        return f'{self.playerInfo.name}\'s role is {self.role.name.lower()}'

class AssumptionType(Enum) :
    NORMAL = 0
    TEST_RESULT = 1
    HEAL_SUCCESS = 2

class Assumption :
    def __init__(self, estimations: list[Estimation], reason: str, assumptionType: AssumptionType = AssumptionType.NORMAL) :
        self.estimations = estimations
        self.reason = reason
        self.assumptionType = assumptionType

    def __str__(self) :
        estimations = ','.join(map(lambda estimation: str(estimation), self.estimations))
        return f'{estimations}[{self.assumptionType.name}] ({self.reason})'

    def __repr__(self) :
        return self.__str__()

    def getPrompt(self) :
        estimations = ', '.join(map(lambda estimation: estimation.getPrompt(), self.estimations)) 
        return f'{estimations} because {self.reason}.'

    def __eq__(self, other) :
        if not isinstance(other, Assumption) :
            return False

        return (
            self.reason == other.reason and
            self.assumptionType == other.assumptionType and
            set(self.estimations) == set(other.estimations)
        )

    def __hash__(self):
        return hash((self.reason, self.assumptionType, frozenset(self.estimations)))

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

            if self.mainMafiaAssumption != None :
                break

        self.estimations: list[Estimation] = [estimation for assumption in assumptions for estimation in assumption.estimations]
        self.mafiaEstimations: list[Estimation] = [estimation for estimation in self.estimations if estimation.role == Role.MAFIA]

    def isEffective(self) :
        return self.publicRole != Role.CITIZEN or len(self.estimations) > 0

    def __str__(self) :
        return f'publicRole={self.publicRole.name.lower()}, assumptions={self.assumptions}'

    def __repr__(self) :
        return self.__str__()

    def assumptionsToStr(self) :
        return str(self.assumptions)

    def assumptionsToPrompt(self) :
        return '\n'.join(map(lambda assumption: 'You must argue that ' + assumption.getPrompt(), self.assumptions))

    def isDefaultReasonIncluded(self) -> bool :
        for assumption in self.assumptions :
            if assumption.reason == defaultReason :
                return True
        return False

    def __eq__(self, other) :
        if not isinstance(other, Strategy) :
            return False

        return (
            self.publicRole == other.publicRole and
            set(self.assumptions) == set(other.assumptions)
        )

    def __hash__(self):
        return hash((self.publicRole, frozenset(self.assumptions)))

class VoteStrategy(Strategy) :
    def __init__(self, playerInfo: PlayerInfo) :
        assumption = Assumption([Estimation(playerInfo, Role.MAFIA)], '')
        super().__init__(
            publicRole=Role.CITIZEN, # not used
            assumptions=[assumption],
        )
