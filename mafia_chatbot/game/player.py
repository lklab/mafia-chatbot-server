from mafia_chatbot.game.player_info import *
from mafia_chatbot.game.strategy import *

TRUST_MIN: float = -100
TRUST_DEFAULT: float = 0
TRUST_MAX: float = 100

class Player :
    pass

class Player :
    def __init__(self, name, isAI) :
        self.isLive = True
        self.info = PlayerInfo(name, isAI)

        # strategies
        self.discussionStrategy: Strategy = None
        self.voteStrategy: VoteStrategy = None
        self.allDiscussionStrategies: list[Strategy] = []
        self.allVoteStrategies = list[VoteStrategy] = []

        # strategy summary
        self.firstMafiaAssumptions: set[PlayerInfo] = set()
        self.citizenAssumptions: set[PlayerInfo] = set()
        self.publicRole = Role.CITIZEN
        self.isContradictoryRole: tuple[bool, tuple[Role, Role]] = (False, (None, None))
        self.voteHistory: list[PlayerInfo] = []
        self.estimationsAsPolice: dict[PlayerInfo, Estimation] = {}

        # trust data
        self.trustPoint: float = 0
        self.trustMainIssue: str = ''

        # police's private data
        self.testResults: dict[Player, Role] = {}

    def __str__(self) :
        return self.info.__str__()

    def __repr__(self) :
        return self.info.__repr__()

    def setDiscussionStrategy(self, round: int, strategy: Strategy) :
        self.discussionStrategy = strategy

        # update allDiscussionStrategies
        self.expandList(self.allDiscussionStrategies, round + 1)
        self.allDiscussionStrategies[round] = strategy

        for assumption in strategy.assumptions :
            for estimation in assumption.estimations :
                # update firstMafiaAssumptions
                if estimation.isFirst and estimation.role == Role.MAFIA :
                    self.firstMafiaAssumptions.add(estimation.playerInfo)

                # update citizenAssumptions
                if estimation.role != Role.CITIZEN :
                    self.citizenAssumptions.add(estimation.playerInfo)
                else :
                    self.citizenAssumptions.discard(estimation.playerInfo)

        # update publicRole
        if self.publicRole != strategy.publicRole :
            if strategy.publicRole == Role.MAFIA :
                self.publicRole = strategy.publicRole
                self.isContradictoryRole = (False, (None, None))
            elif self.publicRole != Role.CITIZEN and strategy.publicRole != Role.CITIZEN :
                self.isContradictoryRole = (True, (self.publicRole, strategy.publicRole))
            else :
                self.publicRole = strategy.publicRole

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

    def getDiscussion(self) :
        return self.discussionStrategy.assumptionsToStr()

    def addTestResult(self, player: Player, role: Role) :
        self.testResults[player] = role

    def setTrustData(self, trustPoint: float, mainIssue: str) :
        self.trustPoint = trustPoint
        self.trustMainIssue = mainIssue

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
