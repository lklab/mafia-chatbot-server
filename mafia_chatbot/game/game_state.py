import random
from datetime import datetime, timedelta, timezone

from mafia_chatbot.game.game_info import *
from mafia_chatbot.game.player_info import PlayerInfo
from mafia_chatbot.game.player import *
from mafia_chatbot.game.chat_data import ChatData, ChatType

from mafia_chatbot.network.messages import *

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

TONES: list[str] = [
    'Affable', 'Amiable', 'Blunt', 'Breezy', 'Casual', 'Charming',
    'Composed', 'Cordial', 'Distant', 'Eloquent', 'Gracious', 'Irascible',
    'Laid-back', 'Melancholic', 'Pensive', 'Pleasant', 'Reserved', 'Sarcastic',
    'Sincere', 'Witty',
]

class Phase(Enum) :
    DAY = 0
    EVENING = 1
    NIGHT = 2

phaseToProtoDict: dict[Phase, game_pb2.Phase] = {
    Phase.DAY: game_pb2.Phase.Phase_DAY,
    Phase.EVENING: game_pb2.Phase.Phase_EVENING,
    Phase.NIGHT: game_pb2.Phase.Phase_NIGHT,
}

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

        ### create players
        self.players: list[Player] = []
        usedNames = set()

        # create human players
        for client in gameInfo.clients :
            self.players.append(Player(
                name=client.name,
                tone='',
                isHuman=True,
                client=client
            ))
            usedNames.add(client.name.lower())

        if gameInfo.localPlayerName != None :
            self.localPlayer: Player = Player(
                name=gameInfo.localPlayerName,
                tone='',
                isHuman=True,
                client=None
            )
            self.players.append(self.localPlayer)
            usedNames.add(gameInfo.localPlayerName.lower())
        else :
            self.localPlayer = None

        # prepare names and tones for bot players
        if gameInfo.language in NAMES :
            names: list[str] = NAMES[gameInfo.language].copy()
        else :
            names: list[str] = NAMES['english'].copy()
        random.shuffle(names)

        tones: list[str] = TONES.copy()
        random.shuffle(tones)

        # create bot players
        nameIndex = 0
        toneIndex = 0

        for i in range(len(self.players), gameInfo.playerCount) :
            while names[nameIndex] in usedNames :
                nameIndex += 1

            self.players.append(Player(
                name=names[nameIndex],
                tone=tones[toneIndex],
                isHuman=False,
                client=None
            ))

            nameIndex += 1
            toneIndex += 1

        # assign role
        random.shuffle(self.players)
        self.mafiaPlayers: list[Player] = []
        self.humanMafiaPlayers: list[Player] = []

        for i in range(gameInfo.mafiaCount) :
            self.players[i].info.role = Role.MAFIA
            self.mafiaPlayers.append(self.players[i])

            if self.players[i].info.isHuman :
                self.humanMafiaPlayers.append(self.players[i])

            if 0.2 > random.random() :
                self.players[i].isFakePolice = True

        self.players[gameInfo.mafiaCount+0].info.role = Role.POLICE
        self.players[gameInfo.mafiaCount+1].info.role = Role.DOCTOR

        self.policePlayer: Player = self.players[gameInfo.mafiaCount+0]
        self.doctorPlayer: Player = self.players[gameInfo.mafiaCount+1]

        # shuffle players
        random.shuffle(self.players)

        ### setup nameList
        self.nameList: list[str] = list(map(lambda p: p.info.name, self.players))

        ### setup allPlayers
        self.allPlayers: list[Player] = self.players.copy()
        self.allMafiaPlayers: list[Player] = self.mafiaPlayers.copy()

        ### setup allPlayerMap
        self.allPlayerMap: dict[PlayerInfo, Player] = {}
        for player in self.allPlayers :
            self.allPlayerMap[player.info] = player

        ### history
        self.chatList: list[ChatData] = []
        self.discussionHistory: list[str] = [] # TODO delete
        self.voteHistory: list[VoteData] = []
        self.removedPlayers: dict[Player, PlayerRemoveInfo] = {}

        ### initialize round
        self.round = 0
        self.currentPhase = Phase.DAY
        self.timeLimit: datetime = None

        ### police data
        self.isPoliceLive = True
        self.publicPolicePlayers: set[Player] = set()
        self.onePublicPolicePlayer: Player = None

        self.isRealPoliveRevealed = False
        self.isFakePoliveRevealed = False

        ### doctor data
        self.isDoctorLive = True

        ### discussion data
        self.firstPointers: dict[Player, Player] = {}

    def removePlayer(self, player: Player, reason: RemoveReason) :
        if player == None or not player.isLive :
            return

        player.isLive = False
        self.players.remove(player)

        if player.info.role == Role.MAFIA :
            self.mafiaPlayers.remove(player)
            if player.info.isHuman :
                self.humanMafiaPlayers.remove(player)

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
            if name.lower() == player.info.name.lower() :
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

    def _switchPhaseDay(self) :
        self._reloadAllChatingCounts()

        self.timeLimit: datetime = datetime.now(timezone.utc) + timedelta(minutes=1)

    def _switchPhaseEvening(self) :
        self._clearAllChatingCounts()

        self.timeLimit: datetime = datetime.now(timezone.utc) + timedelta(seconds=30)

    def _switchPhaseNight(self) :
        self._clearAllChatingCounts()

        self.timeLimit: datetime = datetime.now(timezone.utc) + timedelta(seconds=30)

    _switchPhase = {
        Phase.DAY : _switchPhaseDay,
        Phase.EVENING : _switchPhaseEvening,
        Phase.NIGHT : _switchPhaseNight,
    }

    def _reloadAllChatingCounts(self) :
        for player in self.players :
            if player.info.isHuman :
                player.reloadChatingCount()

    def _clearAllChatingCounts(self) :
        for player in self.players :
            if player.info.isHuman :
                player.clearChatingCount()

    def setPhase(self, phase: Phase) :
        self.currentPhase = phase
        GameState._switchPhase[phase](self)
        self.sendGameStateMessageToAllClient()

    def getCurrentRoundInfo(self) -> RoundInfo :
        return RoundInfo(self.round, len(self.players), len(self.mafiaPlayers))

    def appendDiscussionHistory(self, playerInfo: PlayerInfo, discussion: str) :
        self.discussionHistory.append(f'{playerInfo.name}: {discussion}')

    def appendDiscussionChat(self, sender: PlayerInfo, content: str) :
        chat: ChatData = ChatData(
            type=ChatType.DISCUSSION,
            index=len(self.chatList),
            content=content,
            sender=sender,
        )
        self.chatList.append(chat)
        self.sendAddChatMessageToAllClient(chat)

    def appendSystemChat(self, content: str, receiver: PlayerInfo = None) :
        chat: ChatData = ChatData(
            type=ChatType.SYSTEM,
            index=len(self.chatList),
            content=content,
            receiver=receiver,
        )
        self.chatList.append(chat)
        self.sendAddChatMessageToAllClient(chat)

    def addHumanChat(self, sender: PlayerInfo, chat_pb: game_pb2.Chat) :
        chat: ChatData = ChatData(
            type=ChatType.DISCUSSION,
            index=len(self.chatList),
            content=chat_pb.content,
            sender=sender,
        )

        chat_pb.index = chat.index

        self.chatList.append(chat)
        return chat_pb

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

    def toProtoGameStateMessage(self, player: Player) -> game_pb2.GameState :
        message = game_pb2.GameState()

        message.language = self.gameInfo.language
        message.players.extend(list(map(lambda p : p.toProtoMessage(), self.players)))
        message.me.CopyFrom(player.toProtoMessage())

        message.mafiaCount = self.gameInfo.mafiaCount
        message.remainMafiaCount = self.getMafiaCount()

        message.phase.CopyFrom(self.toProtoGamePhaseMessage())

        return message

    def toProtoGamePhaseMessage(self) -> game_pb2.GamePhase :
        message = game_pb2.GamePhase()

        message.round = self.round
        message.phase = phaseToProtoDict[self.currentPhase]
        message.phaseEndTime.FromDatetime(self.timeLimit)
        message.phaseRemainTime = int((self.timeLimit - datetime.now(timezone.utc)).total_seconds() * 1000)

        return message

    def sendGameStateMessageToAllClient(self) :
        for player in self.players :
            if player.client != None :
                message = self.toProtoGameStateMessage(player)
                player.client.sendMessage(message)

    def sendAddChatMessageToAllClient(self, chat: ChatData) :
        for player in self.players :
            if player.client != None :
                message = chat.toProtoMessage(player.info)
                player.client.sendMessage(message)

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
