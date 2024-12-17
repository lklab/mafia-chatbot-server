import random
import time
from typing import Callable
import gettext

from mafia_chatbot.game.game_info import *
from mafia_chatbot.game.player_info import PlayerInfo
from mafia_chatbot.game.player import *
from mafia_chatbot.game.chat_data import ChatData, ChatType
from mafia_chatbot.game.game_logger import GameLogger, TAG, FakeGameLogger

from mafia_chatbot.network.messages import *

import mafia_chatbot.utils.utils as utils
from mafia_chatbot.utils.name_bank import NAMES, ENGLISH_NAMES

TONES: list[str] = [
    'Affable', 'Amiable', 'Blunt', 'Breezy', 'Casual', 'Charming',
    'Composed', 'Cordial', 'Distant', 'Eloquent', 'Gracious', 'Irascible',
    'Laid-back', 'Melancholic', 'Pensive', 'Pleasant', 'Reserved', 'Sarcastic',
    'Sincere', 'Witty',
]

class Phase(Enum) :
    NOT_PLAYING = 0
    DAY = 1
    EVENING = 2
    NIGHT = 3

phaseToProtoDict: dict[Phase, game_pb2.Phase] = {
    Phase.NOT_PLAYING: game_pb2.Phase.Phase_UNKNOWN,
    Phase.DAY: game_pb2.Phase.Phase_DAY,
    Phase.EVENING: game_pb2.Phase.Phase_EVENING,
    Phase.NIGHT: game_pb2.Phase.Phase_NIGHT,
}

class VoteData :
    def __init__(self, round: int, players: list[Player], clientPlayers: list[Player]) :
        self.round = round
        self.players = players
        self.clientPlayers = clientPlayers

        self.voteDict: dict[PlayerInfo, list[Player]] = {}
        self.voteCount: dict[PlayerInfo, int] = {}

        for player in players :
            self.voteDict[player.info] = []
            self.voteCount[player.info] = 0

        self.isTie = False
        self.targetPlayer: PlayerInfo = None
        self.notVoteTargetPlayers: list[Player] = []

    def setVoteStrategy(self, voter: Player, strategy: VoteStrategy) :
        newTarget: PlayerInfo = strategy.mainTarget
        if newTarget == None :
            return

        oldTarget: PlayerInfo = None
        oldStrategy: VoteStrategy = voter.getVoteStrategy(self.round)
        if oldStrategy != None :
            oldTarget = oldStrategy.mainTarget

        if newTarget != oldTarget :
            if oldTarget != None :
                self.voteDict[oldTarget].remove(voter)
                self.voteCount[oldTarget] -= 1
            self.voteDict[newTarget].append(voter)
            self.voteCount[newTarget] += 1

            voter.setVoteStrategy(self.round, strategy)

            message = self.getVoteStateMessage()
            for player in self.clientPlayers :
                player.client.sendMessage(message)

    def evaluate(self) :
        maxVoteCount = 0

        for playerInfo, vote in self.voteCount.items() :
            if maxVoteCount == vote :
                self.isTie = True
            elif maxVoteCount < vote :
                self.isTie = False
                maxVoteCount = vote
                self.targetPlayer = playerInfo

        targetVotersSet: set[Player] = set()
        for voter in self.voteDict[self.targetPlayer] :
            targetVotersSet.add(voter)

        self.notVoteTargetPlayers: list[Player] = []
        for player in self.players :
            if player not in targetVotersSet and player.info != self.targetPlayer :
                self.notVoteTargetPlayers.append(player)

    def getVoteResultStr(self) -> list[str] :
        targets: list[PlayerInfo] = list(self.voteDict.keys())
        targets.sort(key=lambda target: self.voteCount[target], reverse=True)
        return list(map(lambda t: f'{t.name}({self.voteCount[t]}): {', '.join(map(lambda v: v.info.name, self.voteDict[t]))}', filter(lambda t: self.voteCount[t] > 0, targets)))

    def getVoteStateMessage(self) -> game_pb2.VoteState :
        message = game_pb2.VoteState()
        for target, voters in self.voteDict.items() :
            ids = [voter.info.id for voter in voters]
            message.votersMap[target.id].voters.extend(ids)
        return message

class NightTargetData :
    def __init__(self, round) :
        self.round = round
        self.killTarget: Player = None
        self.testTarget: Player = None
        self.healTarget: Player = None

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

languageToCodeDict: dict[str, str] = {
    'english' : 'en',
    'korean' : 'ko',
}

class GameState :
    def __init__(self, gameInfo: GameInfo, logger: GameLogger = None) :
        self.gameInfo = gameInfo
        self.gameId = gameInfo.gameId
        self.logger = logger or GameLogger(self.gameId, 'log')

        ### l10n
        languageCode: str = languageToCodeDict.get(gameInfo.language)
        if languageCode == None :
            languageCode = 'en'

        self.translation = gettext.translation(
            'messages',
            localedir='mafia_chatbot/locales',
            languages=[languageCode],
            fallback=True,
        )
        self.translate = self.translation.gettext
        self._ = self.translate

        self.translateRole: dict[Role, str] = {
            Role.CITIZEN : self._('Citizen'),
            Role.MAFIA   : self._('Mafia'),
            Role.POLICE  : self._('Police'),
            Role.DOCTOR  : self._('Doctor'),
        }

        ### create players
        self.players: list[Player] = []
        self.clientPlayers: list[Player] = []
        usedNames = set() # 사용된 이름 (인간 사용자의 이름만 들어감)

        # create human players
        self.observerPlayer: Player = None
        observerClientId: str = None
        if gameInfo.debugInfo != None :
            observerClientId: str = gameInfo.debugInfo.observerClientId

        for client in gameInfo.clients :
            clientPlayer: Player = Player(
                name=client.name,
                tone='',
                isHuman=True,
                client=client
            )
            client.setLogger(self.logger)
            self.clientPlayers.append(clientPlayer)

            if client.clientId == observerClientId :
                self.observerPlayer = clientPlayer
                clientPlayer.setRemoved(RemoveReason.OBSERVER)
            else :
                self.players.append(clientPlayer)
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

        # assign role - prepare
        random.shuffle(self.players)
        self.mafiaPlayers: list[Player] = []
        self.humanMafiaPlayers: list[Player] = []

        # assign debug role
        if gameInfo.debugInfo != None and gameInfo.debugInfo.fixedRole != None :
            fixedRolePlayer: Player = None
            for player in self.clientPlayers :
                if player.client.clientId == gameInfo.debugInfo.fixedRoleClientId :
                    fixedRolePlayer = player
                    self.players.remove(fixedRolePlayer)
                    break

            if fixedRolePlayer == None :
                pass
            elif gameInfo.debugInfo.fixedRole == Role.CITIZEN :
                self.players.insert(gameInfo.mafiaCount+2, fixedRolePlayer)
            elif gameInfo.debugInfo.fixedRole == Role.MAFIA :
                self.players.insert(                    0, fixedRolePlayer)
            elif gameInfo.debugInfo.fixedRole == Role.POLICE :
                self.players.insert(gameInfo.mafiaCount+0, fixedRolePlayer)
            elif gameInfo.debugInfo.fixedRole == Role.DOCTOR :
                self.players.insert(gameInfo.mafiaCount+1, fixedRolePlayer)

        # assign role
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

        ### setup english name
        if gameInfo.language != 'english' :
            enNameIndex = 0
            predefinedEnglishNames: set[str] = set(ENGLISH_NAMES.values())

            # 사전 정의된 이름일 경우
            for player in self.players :
                if player.info.name in ENGLISH_NAMES :
                    player.info.englishName = ENGLISH_NAMES[player.info.name]

                # 사전에 정의되지 않은 이름일 경우 임의의 영어 이름을 사용
                else :
                    # 미리 정의된 영어 이름(NAMES['english'])과 다른 언어에서 영어로 번역한 이름(ENGLISH_NAMES.values())이 중복될 가능성이 있으므로 중복 검사
                    while NAMES['english'][enNameIndex] in predefinedEnglishNames :
                        enNameIndex += 1
                    player.info.englishName = NAMES['english'][enNameIndex]
                    enNameIndex += 1

        ### setup nameLists
        self.nameList: list[str] = list(map(lambda p: p.info.name, self.players))
        self.englishNameList: list[str] = list(map(lambda p: p.info.englishName, self.players))

        ### setup allPlayers
        self.allPlayers: list[Player] = self.players.copy()
        self.allMafiaPlayers: list[Player] = self.mafiaPlayers.copy()

        ### setup player maps allPlayerMapByInfo
        self.allPlayerMapByInfo: dict[PlayerInfo, Player] = {}
        self.allPlayerMapById: dict[str, Player] = {}
        self.allPlayerByName: dict[str, Player] = {}
        self.allPlayerByEnglishName: dict[str, Player] = {}

        for player in self.allPlayers :
            self.allPlayerMapByInfo[player.info] = player
            self.allPlayerMapById[player.info.id] = player
            self.allPlayerByName[player.info.name.lower()] = player
            self.allPlayerByEnglishName[player.info.englishName.lower()] = player

        ### history
        self.chatList: list[ChatData] = []
        self.conversationLogs: list[str] = []
        self.chatLogs: list[str] = []
        self.voteHistory: list[VoteData] = []
        self.nightTargetHistory: list[NightTargetData] = []
        self.removedPlayers: dict[Player, PlayerRemoveInfo] = {}

        ### events
        self.onHumanChat: Callable[[ChatData], None] = None

        ### phase data
        self.round = 0
        self.currentPhase = Phase.NOT_PLAYING
        self.daySeconds = 60
        self.eveningSeconds = 30
        self.nightSeconds = 30
        self.timeLimit: float = None

        # phase data - debug
        if gameInfo.debugInfo != None :
            self.daySeconds = gameInfo.debugInfo.daySeconds
            self.eveningSeconds = gameInfo.debugInfo.eveningSeconds
            self.nightSeconds = gameInfo.debugInfo.nightSeconds

        ## debug data
        self.continueOnlyBots: bool = False
        if gameInfo.debugInfo != None :
            self.continueOnlyBots = self.observerPlayer != None or gameInfo.debugInfo.continueOnlyBots

    def removePlayer(self, player: Player, reason: RemoveReason) :
        if player == None or not player.isLive :
            return

        player.setRemoved(reason)
        self.players.remove(player)

        if player.info.role == Role.MAFIA :
            self.mafiaPlayers.remove(player)
            if player.info.isHuman :
                self.humanMafiaPlayers.remove(player)

        # update history
        self.removedPlayers[player] = PlayerRemoveInfo(player, reason, self.getCurrentRoundInfo())

        # send player removed message
        message = game_pb2.Removed()
        message.reason = removeReasonToProtoDict[reason]
        player.client.sendMessage(message)

    def removePlayerByInfo(self, playerInfo: PlayerInfo, reason: RemoveReason) :
        self.removePlayer(self.getPlayerByInfo(playerInfo), reason)

    def getPlayerRemoveInfo(self, player: Player) -> PlayerRemoveInfo :
        return self.removedPlayers.get(player)

    def getPlayerRemoveInfoByInfo(self, playerInfo: PlayerInfo) -> PlayerRemoveInfo :
        return self.getPlayerRemoveInfo(self.getPlayerByInfo(playerInfo))

    def getPlayerByInfo(self, playerInfo: PlayerInfo) -> Player :
        return self.allPlayerMapByInfo.get(playerInfo)

    def getPlayerById(self, id: str) -> Player :
        return self.allPlayerMapById.get(id)

    def getPlayerByName(self, name: str) -> Player :
        name = name.lower()
        if name in self.allPlayerByName :
            return self.allPlayerByName[name]
        return None

    def getPlayerInfoByName(self, name: str) -> PlayerInfo :
        name = name.lower()
        if name in self.allPlayerByName :
            return self.allPlayerByName[name].info
        return None

    def getPlayerByEnglishName(self, name: str) -> Player :
        name = name.lower()
        if name in self.allPlayerByEnglishName :
            return self.allPlayerByEnglishName[name]
        return None

    def getPlayerInfoByEnglishName(self, name: str) -> PlayerInfo :
        name = name.lower()
        if name in self.allPlayerByEnglishName :
            return self.allPlayerByEnglishName[name].info
        return None

    async def getPlayerFromCuiAsync(self, text) -> Player :
        player: Player = None

        while player == None :
            name: str = await utils.getCuiInputAsync(text)
            player = self.getPlayerByName(name)

        return player

    def addRound(self) :
        self.round += 1

    def _switchPhaseDay(self) :
        self._reloadAllChatingCounts()
        self.timeLimit: float = time.monotonic() + self.daySeconds

    def _switchPhaseEvening(self) :
        self._clearAllChatingCounts()
        self.timeLimit: float = time.monotonic() + self.eveningSeconds

    def _switchPhaseNight(self) :
        self._clearAllChatingCounts()
        self.timeLimit: float = time.monotonic() + self.nightSeconds

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
        self.logger.log(TAG.PHASE, f'round={self.round}, phase={self.currentPhase.name}')

        if phase != Phase.NOT_PLAYING :
            GameState._switchPhase[phase](self)
            self.sendGameStateMessageToAllClient()

    def getCurrentRoundInfo(self) -> RoundInfo :
        return RoundInfo(self.round, len(self.players), len(self.mafiaPlayers))

    def appendDiscussionChat(self, sender: PlayerInfo, content: str) :
        chat: ChatData = ChatData(
            type=ChatType.DISCUSSION,
            index=len(self.chatList),
            content=content,
            sender=sender,
        )
        self.chatList.append(chat)
        self.conversationLogs.append(f'{sender.name}: {content}')
        self.chatLogs.append(f'{sender.name}: {content}')
        self.logger.log(TAG.CHAT, f'DISCUSSION - {chat.index} - {sender.name}: {content}')
        self.sendAddChatMessageToAllClient(chat)

    def appendSystemChat(self, content: str, receiver: PlayerInfo = None) :
        chat: ChatData = ChatData(
            type=ChatType.SYSTEM,
            index=len(self.chatList),
            content=content,
            receiver=receiver,
        )
        self.chatList.append(chat)
        if receiver == None :
            self.conversationLogs.append(f'{self._('System')}: {content}')
        self.logger.log(TAG.CHAT, f'SYSTEM - {chat.index} - for {"everyone" if receiver == None else receiver.name}: {content}')
        self.sendAddChatMessageToAllClient(chat)

    def addHumanChat(self, sender: PlayerInfo, chat_out: game_pb2.Chat) :
        chat: ChatData = ChatData(
            type=ChatType.DISCUSSION,
            index=len(self.chatList),
            content=chat_out.content,
            sender=sender,
        )
        self.chatList.append(chat)
        self.conversationLogs.append(f'{sender.name}: {chat.content}')
        self.chatLogs.append(f'{sender.name}: {chat.content}')
        self.logger.log(TAG.CHAT, f'DISCUSSION - {chat.index} - {sender.name}: {chat.content}')

        if self.onHumanChat != None :
            self.onHumanChat(chat)

        chat_out.index = chat.index

    def setOnHumanChatListener(self, listener: Callable[[ChatData], None]) :
        self.onHumanChat = listener

    def getVoteData(self, round: int) -> VoteData :
        if len(self.voteHistory) < round + 1 :
            self.expandList(self.voteHistory, self.round + 1)

        voteData: VoteData = None
        if self.voteHistory[self.round] == None :
            voteData = VoteData(self.round, self.players, self.clientPlayers)
            self.voteHistory[self.round] = voteData
        else :
            voteData = self.voteHistory[self.round]

        return voteData

    def getCurrentVoteData(self) -> VoteData :
        return self.getVoteData(self.round)

    def getNightTargetData(self, round: int) -> NightTargetData :
        if len(self.nightTargetHistory) < round + 1 :
            self.expandList(self.nightTargetHistory, self.round + 1)

        nightTargetData: NightTargetData = None
        if self.nightTargetHistory[self.round] == None :
            nightTargetData = NightTargetData(self.round)
            self.nightTargetHistory[self.round] = nightTargetData
        else :
            nightTargetData = self.nightTargetHistory[self.round]

        return nightTargetData

    def getCurrentNightTargetData(self) -> NightTargetData :
        return self.getNightTargetData(self.round)

    def getPlayerCount(self) -> int :
        return len(self.players)

    def getMafiaCount(self) -> int :
        return len(self.mafiaPlayers)

    def getCitizenCount(self) -> int :
        return self.getPlayerCount() - self.getMafiaCount()

    def toProtoGameStateMessage(self, player: Player) -> game_pb2.GameState :
        message = game_pb2.GameState()

        message.language = self.gameInfo.language
        message.players.extend(list(map(lambda p : p.createProtoMessage(player), self.allPlayers)))
        player.toProtoMessage(player, message.me)

        message.mafiaCount = self.gameInfo.mafiaCount
        message.remainMafiaCount = self.getMafiaCount()

        self.toProtoGamePhaseMessage(message.phase)

        message.remainMyChat = player.remainChatingCount
        message.maxMyChat = player.maxChatingCount

        return message

    def toProtoGamePhaseMessage(self, message_out: game_pb2.GamePhase) :
        message_out.round = self.round
        message_out.phase = phaseToProtoDict[self.currentPhase]
        message_out.phaseEndTime = self.timeLimit
        message_out.phaseRemainTime = self.timeLimit - time.monotonic()

    def sendGameStateMessageToAllClient(self) :
        for player in self.clientPlayers :
            message = self.toProtoGameStateMessage(player)
            player.client.sendMessage(message)

    def sendAddChatMessageToAllClient(self, chat: ChatData) :
        for player in self.clientPlayers :
            message = game_pb2.AddChat()
            chat.toProtoMessage(player.info, message.chat)
            message.remainMyChat = player.remainChatingCount
            message.maxMyChat = player.maxChatingCount
            player.client.sendMessage(message)

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
