from mafia_chatbot.game.player_info import *
from mafia_chatbot.game.strategy import *

class Player :
    pass

class Player :
    def __init__(self, name, isAI) :
        self.isLive = True
        self.info = PlayerInfo(name, isAI)

        self.strategy: Strategy = None
        self.pastStrategies: list[Strategy] = []
        self.allTargets: set[PlayerInfo] = set()

        self.testResults: dict[Player, Role] = {}

    def __str__(self) :
        return self.info.__str__()

    def __repr__(self) :
        return self.info.__repr__()

    def setStrategy(self, strategy: Strategy) :
        pastPublicRole: Role = None

        if self.strategy != None :
            self.pastStrategies.append(self.strategy)
            pastPublicRole = self.strategy.publicRole

        self.strategy = strategy

        if self.strategy.publicRole == None :
            if pastPublicRole != None :
                self.strategy.publicRole = pastPublicRole
            else :
                self.strategy.publicRole = Role.CITIZEN

        for playerInfo, role in self.strategy.assumptions :
            if role == Role.MAFIA :
                self.allTargets.add(playerInfo)

    def addTestResult(self, player: Player, role: Role) :
        self.testResults[player] = role

    def getDiscussion(self) :
        targetsStr = ', '.join(map(lambda playerInfo : playerInfo.name, self.strategy.targets))
        return f'{self.info.name}: 저는 {targetsStr}를 의심합니다.'
