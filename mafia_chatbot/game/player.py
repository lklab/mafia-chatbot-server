from game.player_info import *
from game.strategy import *

class Player :
    def __init__(self, name, isAI) :
        self.isLive = True
        self.info = PlayerInfo(name, isAI)

        self.strategy: Strategy = None
        self.pastStrategies: list[Strategy] = []
        self.allTargets: set[PlayerInfo] = set()

    def __str__(self) :
        return self.info.__str__()

    def __repr__(self) :
        return self.info.__repr__()

    def setStrategy(self, strategy: Strategy) :
        if self.strategy != None :
            self.pastStrategies.append(self.strategy)

        self.strategy = strategy

        for target in self.strategy.targets :
            self.allTargets.add(target)

    def getDiscussion(self) :
        targetsStr = ', '.join(map(lambda playerInfo : playerInfo.name, self.strategy.targets))
        return f'{self.info.name}: 저는 {targetsStr}를 의심합니다.'
