import random
import time
from typing import Callable
import gettext

from mafia_chatbot.game.game_info import *
from mafia_chatbot.game.player_info import PlayerInfo
from mafia_chatbot.game.player import *
from mafia_chatbot.game.chat_data import ChatData, ChatType
from mafia_chatbot.game.game_logger import GameLogger, TAG, FakeGameLogger
from mafia_chatbot.game.kill_cancel_checker import KillCancelChecker

from mafia_chatbot.network.messages import *

import mafia_chatbot.utils.utils as utils
import mafia_chatbot.utils.name_bank as NameBank

TONES: list[str] = [
    'Affable', 'Amiable', 'Blunt', 'Breezy', 'Casual', 'Charming',
    'Composed', 'Cordial', 'Distant', 'Eloquent', 'Gracious', 'Irascible',
    'Laid-back', 'Melancholic', 'Pensive', 'Pleasant', 'Reserved', 'Sarcastic',
    'Sincere', 'Witty',
]

class Phase(Enum) :
    PREPARE = 0
    DAY = 1
    EVENING = 2
    NIGHT = 3
    END = 4

phaseToProtoDict: dict[Phase, game_data_pb2.Phase] = {
    Phase.PREPARE: game_data_pb2.Phase.Phase_PREPARE,
    Phase.DAY: game_data_pb2.Phase.Phase_DAY,
    Phase.EVENING: game_data_pb2.Phase.Phase_EVENING,
    Phase.NIGHT: game_data_pb2.Phase.Phase_NIGHT,
    Phase.END: game_data_pb2.Phase.Phase_END,
}
languageToCodeDict: dict[str, str] = {
    'english' : 'en',
    'korean' : 'ko',
}

class VoteData :
    def __init__(self, round: int, players: list[Player], userPlayers: list[Player]) :
        self.round = round
        self.players = players
        self.userPlayers = userPlayers

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
            for player in self.userPlayers :
                player.user.send(message)

    def evaluate(self) :
        maxVoteCount = 0

        for playerInfo, vote in self.voteCount.items() :
            if maxVoteCount == vote :
                self.isTie = True
            elif maxVoteCount < vote :
                self.isTie = False
                maxVoteCount = vote
                self.targetPlayer = playerInfo

        if self.targetPlayer != None :
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

        def getVotersText(t: PlayerInfo) :
            votersText = ', '.join(map(lambda v: v.info.name, self.voteDict[t]))
            return f'{t.name}({self.voteCount[t]}): {votersText}'
        return list(map(getVotersText, filter(lambda t: self.voteCount[t] > 0, targets)))

    def getVoteStateMessage(self) -> game_pb2.VoteState :
        message = game_pb2.VoteState()
        message.type = game_data_pb2.TargetType.TARGET_VOTE
        for target, voters in self.voteDict.items() :
            ids = [voter.info.id for voter in voters]
            message.votersMap[target.id].voters.extend(ids)
        return message

    def getVoters(self, targetInfo: PlayerInfo) -> list[Player] :
        return self.voteDict[targetInfo]

class KillVoteData :
    def __init__(self, round: int, mafiaUserPlayers: list[Player]) :
        self.round = round
        self.mafiaUserPlayers = mafiaUserPlayers
        self.voteDict: dict[Player, Player] = {}

    def setKillTarget(self, voter: Player, target: Player) :
        if not voter.isLive or voter.info.role != Role.MAFIA :
            return

        if voter not in self.voteDict :
            self.voteDict[voter] = None

        oldTarget: Player = self.voteDict[voter]

        if target != oldTarget :
            self.voteDict[voter] = target

            message = self.getVoteStateMessage()
            for player in self.mafiaUserPlayers :
                player.user.send(message)

    def evaluate(self) -> Player :
        voteCounts: dict[Player, int] = {}
        maxVoteCount = 0

        # 투표 수 집계
        for target in self.voteDict.values():
            if target != None :
                voteCounts[target] = voteCounts.get(target, 0) + 1
                maxVoteCount = max(maxVoteCount, voteCounts[target])

        # 최다 득표자 목록 생성
        targets = [target for target, count in voteCounts.items() if count == maxVoteCount]

        # 동률이면 랜덤으로 선택
        return random.choice(targets) if targets else None

    def getVoteStateMessage(self) -> game_pb2.VoteState :
        message = game_pb2.VoteState()
        message.type = game_data_pb2.TargetType.TARGET_KILL
        for voter, target in self.voteDict.items() :
            message.votersMap[target.info.id].voters.append(voter.info.id)
        return message

class NightTargetData :
    def __init__(self, round: int, mafiaUserPlayers: list[Player]) :
        self.round = round
        self.killVoteData: KillVoteData = KillVoteData(round, mafiaUserPlayers)
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

class GameState :
    def __init__(self, gameInfo: GameInfo, logger: GameLogger = None) :
        self.gameInfo = gameInfo
        self.gameId = gameInfo.gameId
        self.logger = logger or GameLogger(self.gameId, 'log')

        ### l10n
        languageCode: str = languageToCodeDict.get(gameInfo.language, 'en')
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
        self.userPlayers: list[Player] = []
        usedNames = set() # 사용된 이름 (인간 사용자의 이름만 들어감)

        # prepare names and tones
        names: list[str] = NameBank.getCopyAndShuffleNames(gameInfo.language)
        tones: list[str] = TONES.copy()
        random.shuffle(tones)
        nameIndex = 0
        toneIndex = 0

        # create human players
        self.observerPlayer: Player = None
        observerClientId: str = None
        if gameInfo.debugInfo != None :
            observerClientId: str = gameInfo.debugInfo.observerClientId

        for user in gameInfo.users :
            name: str = user.clientName
            while name.lower() in usedNames :
                name = names[nameIndex]
                nameIndex += 1

            userPlayer: Player = Player(
                name=name,
                tone='',
                isHuman=True,
                user=user
            )
            user.setLogger(self.logger)
            self.userPlayers.append(userPlayer)

            if user.clientId == observerClientId :
                self.observerPlayer = userPlayer
                userPlayer.setRemoved(RemoveReason.OBSERVER)
            else :
                self.players.append(userPlayer)
                usedNames.add(userPlayer.info.name.lower())

        if gameInfo.localPlayerName != None :
            name: str = gameInfo.localPlayerName
            while name.lower() in usedNames :
                name = names[nameIndex]
                nameIndex += 1

            self.localPlayer: Player = Player(
                name=name,
                tone='',
                isHuman=True,
                user=None
            )
            self.players.append(self.localPlayer)
            usedNames.add(self.localPlayer.info.name.lower())
        else :
            self.localPlayer = None

        # create bot players
        for i in range(len(self.players), gameInfo.playerCount) :
            while names[nameIndex].lower() in usedNames :
                nameIndex += 1

            self.players.append(Player(
                name=names[nameIndex],
                tone=tones[toneIndex],
                isHuman=False,
                user=None
            ))

            nameIndex += 1
            toneIndex += 1

        # assign role - prepare
        random.shuffle(self.players)
        self.mafiaPlayers: list[Player] = []
        self.humanMafiaPlayers: list[Player] = []

        # assign fixed role
        if gameInfo.fixedRole != None and len(self.userPlayers) == 1 :
            fixedRolePlayer: Player = self.userPlayers[0]
            self.players.remove(fixedRolePlayer)

            if gameInfo.fixedRole == Role.CITIZEN :
                self.players.insert(gameInfo.mafiaCount+2, fixedRolePlayer)
            elif gameInfo.fixedRole == Role.MAFIA :
                self.players.insert(                    0, fixedRolePlayer)
            elif gameInfo.fixedRole == Role.POLICE :
                self.players.insert(gameInfo.mafiaCount+0, fixedRolePlayer)
            elif gameInfo.fixedRole == Role.DOCTOR :
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
            englishNameMaker: NameBank.EnglishNameMaker = NameBank.EnglishNameMaker(gameInfo.language)
            for player in self.players :
                player.info.englishName = englishNameMaker.getEnglishName(player.info.name)

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
        self.voteHistory: list[VoteData] = []
        self.nightTargetHistory: list[NightTargetData] = []
        self.removedPlayers: dict[Player, PlayerRemoveInfo] = {}

        ### events
        self.onHumanChat: Callable[[ChatData], None] = None

        ### phase data
        self.round = 0
        self.currentPhase = Phase.PREPARE
        self.daySeconds = 60
        self.eveningSeconds = 30
        self.nightSeconds = 30
        self.timeLimit: float = time.monotonic()

        # phase data - debug
        if gameInfo.debugInfo != None :
            self.daySeconds = 60 if gameInfo.debugInfo.daySeconds <= 0 else max(gameInfo.debugInfo.daySeconds, 5)
            self.eveningSeconds = 30 if gameInfo.debugInfo.eveningSeconds <= 0 else max(gameInfo.debugInfo.eveningSeconds, 5)
            self.nightSeconds = 30 if gameInfo.debugInfo.nightSeconds <= 0 else max(gameInfo.debugInfo.nightSeconds, 5)

        ### debug data
        self.continueOnlyBots: bool = False
        if gameInfo.debugInfo != None :
            self.continueOnlyBots = self.observerPlayer != None or gameInfo.debugInfo.continueOnlyBots

        ### kill cancel data
        self.killCancelCheckers: dict[Player, KillCancelChecker] = {}

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
        if player.user != None :
            message = game_pb2.Removed()
            message.reason = removeReasonToProtoDict[reason]
            player.user.send(message)

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

    def _switchPhaseNone(self) :
        pass

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
        Phase.PREPARE : _switchPhaseNone,
        Phase.DAY : _switchPhaseDay,
        Phase.EVENING : _switchPhaseEvening,
        Phase.NIGHT : _switchPhaseNight,
        Phase.END : _switchPhaseNone,
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

        GameState._switchPhase[phase](self)
        self.sendGameStateMessageToAllUsers()

    def getCurrentRoundInfo(self) -> RoundInfo :
        return RoundInfo(self.round, len(self.players), len(self.mafiaPlayers))

    def appendDiscussionChat(self, sender: PlayerInfo, content: str) -> ChatData :
        chat: ChatData = ChatData(
            type=ChatType.DISCUSSION,
            index=len(self.chatList),
            content=content,
            sender=sender,
        )
        self.chatList.append(chat)
        self.logger.log(TAG.CHAT, f'DISCUSSION - {chat.index} - {sender.name}: {content}')
        self.sendAddChatMessageToAllUsers(chat)

        return chat

    def appendSystemChat(self, content: str, receiver: PlayerInfo = None) :
        chat: ChatData = ChatData(
            type=ChatType.SYSTEM,
            index=len(self.chatList),
            content=content,
            receiver=receiver,
        )
        self.chatList.append(chat)
        self.logger.log(TAG.CHAT, f'SYSTEM - {chat.index} - for {"everyone" if receiver == None else receiver.name}: {content}')
        self.sendAddChatMessageToAllUsers(chat)

    def addHumanChat(self, sender: PlayerInfo, chat_out: game_data_pb2.Chat) :
        chat: ChatData = ChatData(
            type=ChatType.DISCUSSION,
            index=len(self.chatList),
            content=chat_out.content,
            sender=sender,
            id=chat_out.id,
        )
        self.chatList.append(chat)
        self.logger.log(TAG.CHAT, f'DISCUSSION - {chat.index} - {sender.name}: {chat.content}')

        chat_out.index = chat.index
        self.sendAddChatMessageToAllUsers(chat)

        if self.onHumanChat != None :
            self.onHumanChat(chat)

    def getRecentConversationLogs(self, count: int) -> list[str] :
        logs: list[str] = []
        systemText = self._('System')

        for chat in reversed(self.chatList) :
            if count <= 0 :
                logs.append('(The previous conversation is omitted.)')
                break

            if chat.type == ChatType.DISCUSSION :
                logs.append(f'{chat.sender.name}: {chat.content}')
                count -= 1
            elif chat.receiver == None :
                logs.append(f'{systemText}: {chat.content}')

        return logs[::-1]

    def getDiscussionChatLogs(self, count: int, lastChat: ChatData = None) -> list[str] :
        logs: list[str] = []
        index: int = len(self.chatList) - 1 if lastChat == None else lastChat.index

        while index >= 0 and len(logs) < count :
            chat: ChatData = self.chatList[index]
            if chat.type == ChatType.DISCUSSION :
                logs.append(f'{chat.sender.name}: {chat.content}')
            index -= 1

        return logs[::-1]

    def setOnHumanChatListener(self, listener: Callable[[ChatData], None]) :
        self.onHumanChat = listener

    def getVoteData(self, round: int) -> VoteData :
        if len(self.voteHistory) < round + 1 :
            self.expandList(self.voteHistory, self.round + 1)

        voteData: VoteData = None
        if self.voteHistory[self.round] == None :
            voteData = VoteData(self.round, self.players, self.userPlayers)
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
            nightTargetData = NightTargetData(self.round, [user for user in self.userPlayers if user.info.role == Role.MAFIA])
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

    def getHumanPlayerCount(self) -> int :
        return len(self.userPlayers)

    def getLiveHumanPlayerCount(self) -> int :
        return len(list(filter(lambda player : player.isLive, self.userPlayers)))

    def toProtoGameStateMessage(self, player: Player) -> game_pb2.GameState :
        message = game_pb2.GameState()

        message.language = self.gameInfo.language
        message.players.extend(list(map(lambda p : p.createProtoMessage(player, openRole=self.currentPhase==Phase.END), self.allPlayers)))
        player.toProtoMessage(player, message.me)

        message.mafiaCount = self.gameInfo.mafiaCount
        message.remainMafiaCount = self.getMafiaCount()

        self.toProtoGamePhaseMessage(message.phase)

        message.remainMyChat = player.remainChatingCount
        message.maxMyChat = player.maxChatingCount

        message.canCancelKillWithAds = player in self.killCancelCheckers

        return message

    def toProtoGamePhaseMessage(self, message_out: game_pb2.GamePhase) :
        message_out.round = self.round
        message_out.phase = phaseToProtoDict[self.currentPhase]
        message_out.phaseEndTime = self.timeLimit
        message_out.phaseRemainTime = self.timeLimit - time.monotonic()

    def sendGameStateMessageToAllUsers(self) :
        for player in self.userPlayers :
            message = self.toProtoGameStateMessage(player)
            player.user.send(message)

    def sendAddChatMessageToAllUsers(self, chat: ChatData) :
        for player in self.userPlayers :
            message = game_pb2.AddChat()
            chat.toProtoMessage(player.info, message.chat)
            message.remainMyChat = player.remainChatingCount
            message.maxMyChat = player.maxChatingCount
            player.user.send(message)

    def removeUser(self, user: ClientUser) :
        for userPlayer in self.userPlayers :
            if userPlayer.user == user :
                userPlayer.user = None
                self.userPlayers.remove(userPlayer)
                self.clearKillCancelChecker(userPlayer)
                break

    def startKillCancelChecker(self, player: Player) -> KillCancelChecker :
        checker: KillCancelChecker = KillCancelChecker(player)
        self.killCancelCheckers[player] = checker
        checker.start()
        return checker

    def setKillCancelRequest(self, player: Player, message: game_pb2.CancelKillWithAds) -> bool :
        if player in self.killCancelCheckers :
            self.killCancelCheckers[player].setUserMessage(message)
            del self.killCancelCheckers[player]
            return True
        else :
            return False

    def clearKillCancelChecker(self, player) :
        if player in self.killCancelCheckers :
            self.killCancelCheckers[player].interrupt()
            del self.killCancelCheckers[player]

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)
