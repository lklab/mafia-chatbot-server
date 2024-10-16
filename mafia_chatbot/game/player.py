import random

from mafia_chatbot.game.player_info import *
from mafia_chatbot.game.strategy import *

class Player :
    pass

class TrustRecordType:
    pass

TRUST_MIN: int = -100
TRUST_DEFAULT: int = 0
TRUST_MAX: int = 100

class TrustRecordType(Enum) :
    FIRST_POINT_CITIZEN = 0
    FIRST_POINT_MAFIA = 1
    NOT_VOTE_MAFIA = 2

class TrustRecord :
    def __init__(self, type: TrustRecordType, point: int) :
        if isinstance(point, float) :
            point = round(point)

        self.type = type
        self.point = point

trustRecordTypeToPrompt: dict[TrustRecordType, str] = {
    TrustRecordType.FIRST_POINT_CITIZEN : 'He pointed out the citizen first.',
    TrustRecordType.FIRST_POINT_MAFIA : '',
    TrustRecordType.NOT_VOTE_MAFIA : 'He did not vote for the mafia.',
}

class Player :
    def __init__(self, name, isAI) :
        self.isLive = True
        self.info = PlayerInfo(name, isAI)

        # personal factors
        self.conformity: float = random.uniform(0.5, 1.5) # 1.0
        self.revealFactor: float = random.uniform(0.0, 0.3) # 0.1
        self.selfHealFactor: float = random.uniform(0.7, 1.0) # 0.9
        self.isFakePolice: bool = False

        # strategies
        self.discussionStrategy: Strategy = None
        self.voteStrategy: VoteStrategy = None
        self.allDiscussionStrategies: list[Strategy] = []
        self.allVoteStrategies: list[VoteStrategy] = []

        # strategy summary
        self.publicRole = Role.CITIZEN
        self.isPublicRoleChanged = False
        self.isContradictoryRole: tuple[bool, tuple[Role, Role]] = (False, (None, None))
        self.voteHistory: list[PlayerInfo] = []
        self.estimationsAsPolice: dict[PlayerInfo, Estimation] = {}

        # trust data
        self.trustRecords: list[TrustRecord] = []
        self.trustPoint: int = 0
        self.trustMainIssue: str = ''

        self.isTrustedPolice: bool = False

        # police's private data
        self.testResults: dict[Player, Role] = {}
        self.testedTargets: list[Player] = []

    def __str__(self) :
        return self.info.__str__()

    def __repr__(self) :
        return self.info.__repr__()

    def setDiscussionStrategy(self, round: int, strategy: Strategy) :
        self.discussionStrategy = strategy

        # update allDiscussionStrategies
        self.expandList(self.allDiscussionStrategies, round + 1)
        self.allDiscussionStrategies[round] = strategy

        # update publicRole
        if self.publicRole != strategy.publicRole :
            if strategy.publicRole == Role.MAFIA :
                self.publicRole = strategy.publicRole
                self.isPublicRoleChanged = True
                self.isContradictoryRole = (False, (None, None))
            elif self.publicRole != Role.CITIZEN and strategy.publicRole != Role.CITIZEN :
                self.isContradictoryRole = (True, (self.publicRole, strategy.publicRole))
            else :
                self.publicRole = strategy.publicRole
                self.isPublicRoleChanged = True
        else :
            self.isPublicRoleChanged = False

        # update estimationsAsPolice
        if strategy.publicRole == Role.POLICE :
            for estimation in strategy.estimations :
                self.estimationsAsPolice[estimation.playerInfo] = estimation

    def setVoteStrategy(self, round: int, strategy: VoteStrategy) :
        self.voteStrategy = strategy

        # update allVoteStrategies
        self.expandList(self.allVoteStrategies, round + 1)
        self.allVoteStrategies[round] = strategy

        # update voteHistory
        self.expandList(self.voteHistory, round + 1)
        self.voteHistory[round] = strategy.mainTarget

    def getDiscussionStrategy(self, round: int) -> Strategy :
        if round >= 0 and round < len(self.allDiscussionStrategies) :
            return self.allDiscussionStrategies[round]
        else :
            return None

    def getVoteStrategy(self, round: int) -> VoteStrategy :
        if round >= 0 and round < len(self.allVoteStrategies) :
            return self.allVoteStrategies[round]
        else :
            return None

    def getDiscussion(self) :
        return self.discussionStrategy.assumptionsToStr()

    def addTestResult(self, player: Player, role: Role) :
        self.testResults[player] = role
        self.testedTargets.append(player)

    def setTrustData(self, trustPoint: int, mainIssue: str = '') :
        if isinstance(trustPoint, float) :
            trustPoint = round(trustPoint)

        if trustPoint > TRUST_MAX :
            trustPoint = TRUST_MAX
        elif trustPoint < TRUST_MIN :
            trustPoint = TRUST_MIN

        self.trustPoint = trustPoint
        self.trustMainIssue = mainIssue

    def addTrustRecord(self, trustRecord: TrustRecord) :
        self.trustRecords.append(trustRecord)
        print(f'[addTrustRecord] {self.info.name}: {trustRecord.type.name}, {trustRecord.point}')

    def updateTrustDataByRecord(self) :
        pointDict: dict[TrustRecordType, int] = {}

        for record in self.trustRecords :
            if record.type in pointDict :
                pointDict[record.type] += record.point
            else :
                pointDict[record.type] = record.point
        
        total = 0
        maxDecreasePoint = 0
        mainIssue = ''

        for type in pointDict :
            point = pointDict[type]
            total += point
            if point < maxDecreasePoint :
                maxDecreasePoint = point
                mainIssue = trustRecordTypeToPrompt[type]

        self.setTrustData(total, mainIssue)

    def setTrustedPolice(self) :
        self.isTrustedPolice = True

    def getRolePrompt(self) -> str :
        if self.isPublicRoleChanged :
            return f'You must claim that your role is {self.info.role.name.lower()}.'
        else :
            return ''

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
