from mafia_chatbot.game.player_info import *
from mafia_chatbot.game.strategy import *

class Player :
    pass

class Player :
    def __init__(self, name, isAI) :
        self.isLive = True
        self.info = PlayerInfo(name, isAI)

        # strategies
        self.discussionStrategy: Strategy = None
        self.voteStrategy: Strategy = None
        self.allDiscussionStrategies: list[Strategy] = []
        self.allVoteStrategies = list[Strategy] = []

        # strategy summary
        self.firstMafiaAssumptions: set[PlayerInfo] = set()
        self.citizenAssumptions: set[PlayerInfo] = set()
        self.publicRole = Role.CITIZEN
        self.voteHistory: list[PlayerInfo] = []

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
            for estimate in assumption.estimates :
                # update firstMafiaAssumptions
                if estimate.isFirst and estimate.role == Role.MAFIA :
                    self.firstMafiaAssumptions.add(estimate.playerInfo)

                # update citizenAssumptions
                if estimate.role != Role.CITIZEN :
                    self.citizenAssumptions.add(estimate.playerInfo)
                else :
                    self.citizenAssumptions.discard(estimate.playerInfo)

        # update publicRole
        self.publicRole = strategy.publicRole

    def setVoteStrategy(self, round: int, strategy: Strategy) :
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

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
