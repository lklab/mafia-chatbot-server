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

        # create players
        self.humanPlayer = Player(gameInfo.humanName, False)

        names = NAMES.copy()
        random.shuffle(names)

        self.players = [Player(names[i], True) for i in range(gameInfo.playerCount-1)]
        self.players.insert(random.randint(0, gameInfo.playerCount-1), self.humanPlayer)

        # assign role
        self.mafiaPlayers: list[Player] = []
        for i in range(gameInfo.mafiaCount) :
            self.players[i].info.role = Role.MAFIA
            self.mafiaPlayers.append(self.players[i])

        self.players[gameInfo.mafiaCount+0].info.role = Role.POLICE
        self.players[gameInfo.mafiaCount+1].info.role = Role.DOCTOR

        # shuffle player order
        random.shuffle(self.players)

        # setup allPlayers
        self.allPlayers: list[Player] = self.players.copy()

        # setup allPlayerMap
        self.allPlayerMap: dict[PlayerInfo, Player] = {}
        for player in self.allPlayers :
            self.allPlayerMap[player.info] = player

    def removePlayer(self, player: Player) :
        if player == None or not player.isLive :
            return

        player.isLive = False
        self.players.remove(player)

        if player.info.role == Role.MAFIA :
            self.mafiaPlayers.remove(player)

    def removePlayerByInfo(self, playerInfo: PlayerInfo) :
        self.removePlayer(self.getPlayerByInfo(playerInfo))

    def getPlayerByInfo(self, playerInfo: PlayerInfo) -> Player :
        return self.allPlayerMap.get(playerInfo)

    def getPlayerByName(self, name: str) -> Player :
        for player in self.allPlayers :
            if name == player.info.name :
                return player
        return None
