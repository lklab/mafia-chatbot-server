from game.player_info import *
from game.strategy import *

class Player :
    def __init__(self, playerInfo: PlayerInfo) :
        self.info = playerInfo
        self.strategy = None

    def __str__(self) :
        return self.info.__str__()

    def __repr__(self) :
        return self.info.__repr__()

    def setStrategy(self, strategy: Strategy) :
        self.strategy = strategy

    def getDiscussion(self) :
        targetsStr = ', '.join(map(lambda playerInfo : playerInfo.name, self.strategy.targets))
        return f'{self.info.name}: 저는 {targetsStr}를 의심합니다.'
