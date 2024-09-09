import random

from game.game_info import *
from game.player_info import *
from game.player import *

NAMES = [
    'Oliver', 'Emma', 'Noah', 'Ava', 'Liam', 'Sophia', 'Mason', 'Isabella',
    'James', 'Mia', 'Benjamin', 'Amelia', 'Ethan', 'Harper', 'Lucas',
    'Charlotte', 'Henry', 'Evelyn', 'Jack', 'Grace'
]

class GameState :
    def __init__(self, gameInfo: GameInfo) :
        self.gameInfo = gameInfo
        humanPlayerInfo = PlayerInfo(gameInfo.humanName, False)
        self.humanPlayer = Player(humanPlayerInfo)

        names = NAMES.copy()
        random.shuffle(names)

        self.players = [Player(PlayerInfo(names[i], True)) for i in range(gameInfo.playerCount-1)]
        self.players.insert(random.randint(0, gameInfo.playerCount-1), self.humanPlayer)

        for i in range(gameInfo.mafiaCount) :
            self.players[i].info.role = Role.MAFIA
        self.players[gameInfo.mafiaCount+0].info.role = Role.POLICE
        self.players[gameInfo.mafiaCount+1].info.role = Role.DOCTOR
        random.shuffle(self.players)

    def removePlayerByInfo(self, playerInfo: PlayerInfo) :
        for player in self.players :
            if player.info == playerInfo :
                break
        self.players.remove(player)
