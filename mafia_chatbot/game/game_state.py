import random

from game.game_info import *
from game.player import *

NAMES = [
    'Oliver', 'Emma', 'Noah', 'Ava', 'Liam', 'Sophia', 'Mason', 'Isabella',
    'James', 'Mia', 'Benjamin', 'Amelia', 'Ethan', 'Harper', 'Lucas',
    'Charlotte', 'Henry', 'Evelyn', 'Jack', 'Grace'
]

class GameState :
    def __init__(self, gameInfo: GameInfo) :
        self.gameInfo = gameInfo
        self.humanPlayer = Player(gameInfo.humanName, False)

        names = NAMES.copy()
        random.shuffle(names)

        self.players = [Player(names[i], True) for i in range(gameInfo.playerCount-1)]
        self.players.insert(random.randint(0, gameInfo.playerCount-1), self.humanPlayer)

        for i in range(gameInfo.mafiaCount) :
            self.players[i].role = Role.MAFIA
        self.players[gameInfo.mafiaCount+0].role = Role.POLICE
        self.players[gameInfo.mafiaCount+1].role = Role.DOCTOR
        random.shuffle(self.players)
