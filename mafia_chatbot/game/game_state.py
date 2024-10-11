import random

from mafia_chatbot.game.game_info import *
from mafia_chatbot.game.player_info import *
from mafia_chatbot.game.player import *

NAMES = [
    'Oliver', 'Emma', 'Noah', 'Ava', 'Liam', 'Sophia', 'Mason', 'Isabella',
    'James', 'Mia', 'Benjamin', 'Amelia', 'Ethan', 'Harper', 'Lucas',
    'Charlotte', 'Henry', 'Evelyn', 'Jack', 'Grace'
]

class RemoveReason(Enum) :
    VOTE = 0
    KILL = 1

class RoundInfo :
    def __init__(self, round: int, playerCount: int, mafiaCount: int) :
        self.round = round
        self.playerCount = playerCount
        self.mafiaCount = mafiaCount

class PlayerRemoveInfo :
    def __init__(self, player: Player, reason: RemoveReason, roundInfo: RoundInfo) :
        self.player = player
        self.reason = reason
        self.roundInfo = roundInfo

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

        self.policePlayer: Player = self.players[gameInfo.mafiaCount+0]
        self.doctorPlayer: Player = self.players[gameInfo.mafiaCount+1]

        # shuffle player order
        random.shuffle(self.players)

        # setup allPlayers
        self.allPlayers: list[Player] = self.players.copy()
        self.allMafiaPlayers: list[Player] = self.mafiaPlayers.copy()

        # setup allPlayerMap
        self.allPlayerMap: dict[PlayerInfo, Player] = {}
        for player in self.allPlayers :
            self.allPlayerMap[player.info] = player

        # history
        self.discussionHistory: list[str] = []
        self.removedPlayers: dict[Player, PlayerRemoveInfo] = {}

        # initialize round
        self.round = 0

        # shortcut data
        self.isPoliceLive = True
        self.publicPolicePlayers: set[Player] = []
        self.onePublicPolicePlayer: Player = None

    def removePlayer(self, player: Player, reason: RemoveReason) :
        if player == None or not player.isLive :
            return

        player.isLive = False
        self.players.remove(player)

        if player.info.role == Role.MAFIA :
            self.mafiaPlayers.remove(player)

        # update history
        self.removedPlayers[player] = PlayerRemoveInfo(player, reason, self.getCurrentRoundInfo())

        # update shortcut data
        if player.info.role == Role.POLICE :
            self.isPoliceLive = False

        self.publicPolicePlayers.discard(player)
        if len(self.publicPolicePlayers) == 1 :
            self.onePublicPolicePlayer = next(iter(self.publicPolicePlayers))
        else :
            self.onePublicPolicePlayer = None

    def removePlayerByInfo(self, playerInfo: PlayerInfo, reason: RemoveReason) :
        self.removePlayer(self.getPlayerByInfo(playerInfo), reason)

    def getPlayerRemoveInfo(self, player: Player) -> PlayerRemoveInfo :
        return self.removedPlayers.get(player)

    def getPlayerRemoveInfoByInfo(self, playerInfo: PlayerInfo) -> PlayerRemoveInfo :
        return self.getPlayerRemoveInfo(self.getPlayerByInfo(playerInfo))

    def getPlayerByInfo(self, playerInfo: PlayerInfo) -> Player :
        return self.allPlayerMap.get(playerInfo)

    def getPlayerByName(self, name: str) -> Player :
        for player in self.allPlayers :
            if name == player.info.name :
                return player
        return None

    def getPlayerInfoByName(self, name: str) -> PlayerInfo :
        player: Player = self.getPlayerByName(name)
        if player != None :
            return player.info
        else :
            return None

    def addRound(self) :
        self.round += 1

    def getCurrentRoundInfo(self) -> RoundInfo :
        return RoundInfo(self.round, len(self.players), len(self.mafiaPlayers))

    def appendDiscussionHistory(self, playerInfo: PlayerInfo, discussion: str) :
        self.discussionHistory.append(f'{playerInfo.name}: {discussion}')

    def addPublicPolice(self, player: Player) :
        self.publicPolicePlayers.add(player)
        if len(self.publicPolicePlayers) == 1 :
            self.onePublicPolicePlayer = player
        else :
            self.onePublicPolicePlayer = None
