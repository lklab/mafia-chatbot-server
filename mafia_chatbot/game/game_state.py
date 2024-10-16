import random

from mafia_chatbot.game.game_info import *
from mafia_chatbot.game.player_info import *
from mafia_chatbot.game.player import *

NAMES: dict[str, list[str]] = {
    'english' : [
        'Oliver', 'Emma', 'Noah', 'Ava', 'Liam', 'Sophia', 'Mason', 'Isabella',
        'James', 'Mia', 'Benjamin', 'Amelia', 'Ethan', 'Harper', 'Lucas',
        'Charlotte', 'Henry', 'Evelyn', 'Jack', 'Grace',
    ],
    'korean' : [
        '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
        '연우', '소윤', '유진', '성민', '은비', '재현', '예린',
        '태윤', '민지', '시우', '세영', '아린', '진우',
    ],
}

class Phase(Enum) :
    DAY = 0
    EVENING = 1
    NIGHT = 2

class VoteData :
    def __init__(self, round: int, players: list[Player]) :
        self.round = round

        self.voteDict: dict[PlayerInfo, list[Player]] = {}
        self.voteCount: dict[PlayerInfo, int] = {}
        for player in players :
            strategy: Strategy = player.getVoteStrategy(round)
            if strategy != None :
                target = strategy.mainTarget
                if target == None :
                    continue
                elif target not in self.voteDict :
                    self.voteDict[target] = [player]
                    self.voteCount[target] = 1
                else :
                    self.voteDict[target].append(player)
                    self.voteCount[target] += 1

        self.isTie = False
        self.maxVoteCount = 0
        self.targetPlayer: PlayerInfo = None

        for playerInfo, vote in self.voteCount.items() :
            if self.maxVoteCount == vote :
                self.isTie = True
            elif self.maxVoteCount < vote :
                self.isTie = False
                self.maxVoteCount = vote
                self.targetPlayer = playerInfo

        self.notVoteTargetPlayers: list[Player] = []
        for playerInfo, votePlayers in self.voteDict.items() :
            if playerInfo != self.targetPlayer :
                self.notVoteTargetPlayers += votePlayers

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
        if gameInfo.humanName != None :
            self.humanPlayer: Player = Player(gameInfo.humanName, False)
            aiPlayerCount = gameInfo.playerCount - 1
        else :
            self.humanPlayer: Player = None
            aiPlayerCount = gameInfo.playerCount

        if gameInfo.language in NAMES :
            names: list[str] = NAMES[gameInfo.language].copy()
        else :
            names: list[str] = NAMES['english'].copy()

        random.shuffle(names)
        self.players = [Player(names[i], True) for i in range(aiPlayerCount)]

        if self.humanPlayer != None :
            self.players.insert(random.randint(0, aiPlayerCount), self.humanPlayer)

        # assign role
        self.mafiaPlayers: list[Player] = []
        for i in range(gameInfo.mafiaCount) :
            self.players[i].info.role = Role.MAFIA
            self.mafiaPlayers.append(self.players[i])

            if 0.2 > random.random() :
                self.players[i].isFakePolice = True

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
        self.voteHistory: list[VoteData] = []
        self.removedPlayers: dict[Player, PlayerRemoveInfo] = {}

        # initialize round
        self.round = 0
        self.currentPhase = Phase.DAY

        # police data
        self.isPoliceLive = True
        self.publicPolicePlayers: set[Player] = set()
        self.onePublicPolicePlayer: Player = None

        self.isRealPoliveRevealed = False
        self.isFakePoliveRevealed = False

        # doctor data
        self.isDoctorLive = True

        # discussion data
        self.firstPointers: dict[Player, Player] = {}

    def removePlayer(self, player: Player, reason: RemoveReason) :
        if player == None or not player.isLive :
            return

        player.isLive = False
        self.players.remove(player)

        if player.info.role == Role.MAFIA :
            self.mafiaPlayers.remove(player)

        # update history
        self.removedPlayers[player] = PlayerRemoveInfo(player, reason, self.getCurrentRoundInfo())

        # update police data
        self.publicPolicePlayers.discard(player)

        if player.info.role == Role.POLICE :
            self.isPoliceLive = False
            self.onePublicPolicePlayer = player
            player.setTrustedPolice()
        else :
            if len(self.publicPolicePlayers) == 1 :
                self.onePublicPolicePlayer = next(iter(self.publicPolicePlayers))
            else :
                self.onePublicPolicePlayer = None

        # update doctor data
        if player.info.role == Role.DOCTOR :
            self.isDoctorLive = False

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

    def setPhase(self, phase: Phase) :
        self.currentPhase = phase

    def getCurrentRoundInfo(self) -> RoundInfo :
        return RoundInfo(self.round, len(self.players), len(self.mafiaPlayers))

    def appendDiscussionHistory(self, playerInfo: PlayerInfo, discussion: str) :
        self.discussionHistory.append(f'{playerInfo.name}: {discussion}')

    def updateVoteHistory(self) -> VoteData :
        self.expandList(self.voteHistory, self.round + 1)
        voteData = VoteData(self.round, self.players)
        self.voteHistory[self.round] = voteData
        return voteData

    def getVoteData(self, round: int) :
        if round >= 0 and round < len(self.voteHistory) :
            return self.voteHistory[round]
        else :
            return None

    def getCurrentVoteData(self) :
        return self.getVoteData(self.round)

    def addPublicPolice(self, player: Player) :
        self.publicPolicePlayers.add(player)

        if self.isPoliceLive :
            if len(self.publicPolicePlayers) == 1 :
                self.onePublicPolicePlayer = player
            else :
                self.onePublicPolicePlayer = None

        if player.info.role == Role.POLICE :
            self.isRealPoliveRevealed = True
        else :
            self.isFakePoliveRevealed = True

    def getPlayerCount(self) -> int :
        return len(self.players)

    def getMafiaCount(self) -> int :
        return len(self.mafiaPlayers)

    def getCitizenCount(self) -> int :
        return self.getPlayerCount() - self.getMafiaCount()

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
