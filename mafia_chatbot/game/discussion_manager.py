import random
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Deque
from collections import deque

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import Role
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.strategy import Strategy, Assumption, AssumptionType, Estimation
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.chat_data import ChatData
from mafia_chatbot.game.game_logger import GameLogger, TAG

import  mafia_chatbot.utils.utils as utils

class DiscussionManager :
    pass

class DiscussionPlayer :
    def __init__(self, player: Player) :
        self.player: Player = player
        self.discussionCount: int = 0

    def addDiscussionCount(self) :
        self.discussionCount += 1

class DiscussionData :
    def __init__(self, speaker: Player, strategy: Strategy = None, respondent: Player = None, response: str = None) :
        self.speaker = speaker
        self.strategy = strategy
        self.respondent = respondent
        self.response = response

class ResponseContent :
    def __init__(self, player: Player, strategy: Strategy = None, message: str = None) :
        self.player = player
        self.strategy = strategy
        self.message = message

    def __str__(self) :
        return f'{self.player.info.name}: {self.strategy if self.strategy != None else self.message}'

    def __repr__(self) :
        return self.__str__()

class DiscussionManager :
    def __init__(self, gameState: GameState, trustRecorder: TrustRecorder, llm: LLM) :
        self.gameState: GameState = gameState
        self.trustRecorder: TrustRecorder = trustRecorder
        self.llm: LLM = llm
        self.logger: GameLogger = gameState.logger

        self._isRunning: bool = False
        self._normalDiscussionTask: asyncio.Task = None
        self._responseDiscussionTask: asyncio.Task = None

        self.gameState.setOnHumanChatListener(self._onHumanChat)

    def start(self) :
        self.logger.log(TAG.DISCUSSION, 'start discussion')

        # initialize variables
        self._isRunning = True
        self._allDiscussionCount: int = 0
        self._processingHumanDiscussionCount: int = 0
        self._lastDiscussionTime: datetime = datetime.now()
        self._responseContentQueue: Deque[ResponseContent] = deque()

        # setup dPlayers
        players: list[Player] = list(filter(lambda p: not p.info.isHuman, self.gameState.players))
        weights: list[float] = list(map(lambda p: p.positiveness, players))
        self.dPlayers: list[DiscussionPlayer] = []

        while len(players) > 0 :
            index: int = random.choices(range(len(players)), weights=weights, k=1)[0]
            player: Player = players[index]
            self.dPlayers.append(DiscussionPlayer(player))

            del players[index]
            del weights[index]

        self.dPlayersByPlayer: dict[Player, DiscussionPlayer] = {}
        for dPlayer in self.dPlayers :
            self.dPlayersByPlayer[dPlayer.player] = dPlayer

        # process local player
        asyncio.create_task(self._processLocalPlayer())

        # generate first discussion
        self._generateNormalDiscussion()

    async def stop(self) :
        self.logger.log(TAG.DISCUSSION, 'stop discussion')

        self._stopTask()
        self._isRunning = False

        await utils.waitUntil(self._isNotProcessingHumanDiscussion)

        self.logger.log(TAG.DISCUSSION, 'stop discussion completed')

    def _generateDiscussion(self, lastDiscussionData: DiscussionData) :
        if not self._isRunning :
            return

        if lastDiscussionData != None :
            if lastDiscussionData.strategy != None :
                for getter in DiscussionManager._responseContentGetters :
                    content: ResponseContent = getter(self, lastDiscussionData)
                    if content != None :
                        self.logger.log(TAG.DISCUSSION, f'Response content: {content}')
                        self._responseContentQueue.append(content)
                        break
            elif lastDiscussionData.respondent != None :
                content: ResponseContent = ResponseContent(lastDiscussionData.respondent, message=lastDiscussionData.response)
                self.logger.log(TAG.DISCUSSION, f'Response content: {content}')
                self._responseContentQueue.append(content)

        if len(self._responseContentQueue) > 0 :
            self._generateResponseDiscussion()
        else :
            self._generateNormalDiscussion()

    def _generateResponseDiscussion(self) :
        if self._responseDiscussionTask != None :
            return
        self._stopTask()

        content: ResponseContent = self._responseContentQueue[0]
        self._responseDiscussionTask = asyncio.create_task(self._generateResponseDiscussionTask(content))

    async def _generateResponseDiscussionTask(self, content: ResponseContent) :
        # get info
        dPlayer: DiscussionPlayer = self.dPlayersByPlayer[content.player]
        discussionTime: datetime = datetime.now()

        if content.strategy != None :
            # publish discussion
            await self._generateAndPublishDiscussion(dPlayer, content.strategy, discussionTime)
            if not self._isRunning :
                return
        else :
            # publish discussion
            self._publishDiscussion(dPlayer, content.message, discussionTime)

        # remove content form queue
        self._responseContentQueue.popleft()
        self._responseDiscussionTask = None

        # generate next discussion
        if content.strategy != None :
            self._generateDiscussion(DiscussionData(content.player, strategy=content.strategy))
        else :
            self._generateDiscussion(None)

    def _generateNormalDiscussion(self) :
        self._stopTask()

        # select player
        dPlayer: DiscussionPlayer = self.dPlayers[0]

        # decide discussion time
        discussionTime: datetime = self._lastDiscussionTime + timedelta(seconds=random.uniform(5.0, 10.0))

        # start task
        self._normalDiscussionTask = asyncio.create_task(self._generateNormalDiscussionTask(dPlayer, discussionTime))

    async def _generateNormalDiscussionTask(self, dPlayer: DiscussionPlayer, discussionTime: datetime) :
        # wait for discussion time
        waitTime: float = (discussionTime - datetime.now()).total_seconds()
        await asyncio.sleep(waitTime)
        if not self._isRunning :
            return

        # evaluate strategy
        self.trustRecorder.updateTrustRecords()
        strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, dPlayer.player)

        # publish discussion
        await self._generateAndPublishDiscussion(dPlayer, strategy, discussionTime)
        if not self._isRunning :
            return

        # generate next discussion
        self._generateDiscussion(DiscussionData(dPlayer.player, strategy=strategy))

    async def _generateAndPublishDiscussion(self, dPlayer: DiscussionPlayer, strategy: Strategy, discussionTime: datetime) :
        # generate discussion
        if self.gameState.gameInfo.useLLM :
            self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: isRunning={self._isRunning} call getDiscussion') # TODO delete
            discussion: str = await self.llm.getDiscussion(dPlayer.player, strategy)
            self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: isRunning={self._isRunning} getDiscussion result = {discussion}') # TODO delete
            if not self._isRunning :
                return
            discussion = discussion.removeprefix(f'{dPlayer.player.info.name}: ')
            self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: removeprefix = {discussion}') # TODO delete
        else :
            discussion: str = str(strategy)

        # apply strategy and discussion
        self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: call setDiscussionStrategy') # TODO delete
        dPlayer.player.setDiscussionStrategy(self.gameState.round, strategy)

        # record trust info
        self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: call discussionStrategyUpdated') # TODO delete
        self.trustRecorder.discussionStrategyUpdated(dPlayer.player.info, strategy)

        # publish discussion
        self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: call _publishDiscussion') # TODO delete
        self._publishDiscussion(dPlayer, discussion, discussionTime)
        self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: _generateAndPublishDiscussion finished') # TODO delete

    def _publishDiscussion(self, dPlayer: DiscussionPlayer, discussion: str, discussionTime: datetime) :
        # set last discussion time
        self._lastDiscussionTime = discussionTime

        # add chat
        self.gameState.appendDiscussionChat(dPlayer.player.info, discussion)

        # rearrange player
        self._allDiscussionCount += 1
        dPlayer.addDiscussionCount()
        self.dPlayers.remove(dPlayer)

        power: float = dPlayer.player.positiveness * self._allDiscussionCount / (dPlayer.discussionCount * (len(self.dPlayers) + 1))
        power = min(power, 1.0)
        index: int = round(pow(random.random(), power) * len(self.dPlayers))
        self.dPlayers.insert(index, dPlayer)

    async def _processLocalPlayer(self) :
        if self.gameState.localPlayer != None :
            player: Player = self.gameState.localPlayer

            while True :
                discussion: str = await utils.getCuiInputAsync('Enter your discussion: ')
                if not self._isRunning :
                    return

                # process discussion
                await self._processHumanDiscussionTask(player, discussion)
                if not self._isRunning :
                    return

    def _onHumanChat(self, chat: ChatData) :
        # check state
        if not self._isRunning :
            return

        # process discussion
        player: Player = self.gameState.getPlayerByInfo(chat.sender)
        asyncio.create_task(self._processHumanDiscussionTask(player, chat.content))

    async def _processHumanDiscussionTask(self, player: Player, discussion: str) :
        discussionData: DiscussionData = None

        # 인간 사용자의 토론은 처리가 완료될 때까지 낮 phase에서 대기해야 함
        self._processingHumanDiscussionCount += 1

        try :
            discussionData = await self._processHumanDiscussion(player, discussion)
        except Exception as e :
            self.logger.logError("[DiscussionManager] Exception in _processHumanDiscussionTask()", e)

        self._processingHumanDiscussionCount -= 1

        if discussionData == None :
            return

        if discussionData.strategy != None :
            # apply strategy and discussion
            player.setDiscussionStrategy(self.gameState.round, discussionData.strategy)

            # record trust info
            self.trustRecorder.discussionStrategyUpdated(player.info, discussionData.strategy)

        # add chat
        if player.info.isLocalPlayer :
            self.gameState.appendDiscussionChat(player.info, discussion)

        # generate next discussion
        self._generateDiscussion(discussionData)

    async def _processHumanDiscussion(self, player: Player, discussion: str) -> DiscussionData :
        discussionData: DiscussionData = None

        if self.gameState.gameInfo.useLLM :
            conversation: list[str] = self.gameState.chatLogs.copy()

            try :
                containsEstimation: bool = await self.llm.checkContainsEstimation(discussion)

                if containsEstimation :
                    strategy: Strategy = await self.llm.analyzeHumanMessage(player, discussion)
                    if strategy == None :
                        return None
                    discussionData = DiscussionData(player, strategy=strategy)
                else :
                    isQuestion: bool = await self.llm.isMessageQuestion(discussion)
                    if not isQuestion and 0.5 > random.random() :
                        isQuestion = True

                    if isQuestion :
                        respondent, response = await self.llm.generateResponse(player, conversation)
                        if respondent == None :
                            return None
                        discussionData = DiscussionData(player, respondent=respondent, response=response)

            except Exception as e :
                self.logger.logError("[DiscussionManager] Exception in _processHumanDiscussion()", e)
                return None

        else :
            target: Player = self.gameState.getPlayerByName(discussion)
            if target == None :
                return None
            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, target.info, '')
            discussionData = DiscussionData(player, strategy=strategy)
            self.logger.log(TAG.STRATEGY, f'{player.info.name}: strategy is {strategy}')

        return discussionData

    def _isNotProcessingHumanDiscussion(self) -> bool :
        self.logger.log(TAG.DISCUSSION, 'waiting for processing human discussion')
        return self._processingHumanDiscussionCount == 0

    # 마피아 플레이어의 경찰 주장
    def _getResponseContent_claimePoliceForMafia(self, data: DiscussionData) -> ResponseContent :
        if data.strategy == None :
            return None

        if data.speaker.publicRole == Role.POLICE :
            for player in self.gameState.players :
                if player == data.speaker or player.info.isHuman :
                    continue
                if player.publicRole == Role.CITIZEN and player.info.role == Role.MAFIA :
                    strategy: Strategy = evaluator.claimePoliceForMafiaResponse(self.gameState, self.trustRecorder, player)
                    if strategy != None :
                        return ResponseContent(player, strategy=strategy)

        return None

    # 경찰 플레이어의 경찰 주장
    def _getResponseContent_claimePoliceForPolice(self, data: DiscussionData) -> ResponseContent :
        if data.strategy == None :
            return None

        if data.speaker.publicRole == Role.POLICE :
            police: Player = self.gameState.policePlayer
            if not police.info.isHuman and police.isLive and police.publicRole == Role.CITIZEN :
                strategy: Strategy = evaluator.claimePoliceForPoliceResponse(self.gameState, self.trustRecorder, police)
                if strategy != None :
                    return ResponseContent(police, strategy=strategy)

        return None

    # 의사 플레이어의 의사 주장
    def _getResponseContent_claimeDoctorForDoctor(self, data: DiscussionData) -> ResponseContent :
        if data.strategy == None :
            return None

        doctor: Player = self.gameState.doctorPlayer
        if not doctor.info.isHuman and doctor.isLive and doctor.publicRole == Role.CITIZEN :
            strategy: Strategy = evaluator.claimeDoctorForDoctorResponse(self.gameState, self.trustRecorder, doctor)
            if strategy != None :
                return ResponseContent(doctor, strategy=strategy)

        return None

    # 내가 지목당함
    def _getResponseContent_iampointed(self, data: DiscussionData) -> ResponseContent :
        if data.strategy == None :
            return None

        for estimation in data.strategy.mafiaEstimations :
            player: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
            if player == data.speaker or player.info.isHuman :
                continue
            if player.positiveness * player.positiveness > random.random() : # 낮은 확률로 반박
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, player)
                strategy.assumptions[0].reason = 'You claim that you are not the mafia. And you suspect someone else of being the mafia. ' + strategy.assumptions[0].reason
                return ResponseContent(player, strategy=strategy)

        return None

    # 경찰이 나를 지목함
    def _getResponseContent_thePolicePointedMe(self, data: DiscussionData) -> ResponseContent :
        if data.strategy == None :
            return None

        if data.speaker.publicRole == Role.POLICE :
            for assumption in data.strategy.assumptions :
                if assumption.assumptionType == AssumptionType.TEST_RESULT :
                    for estimation in assumption.estimations :
                        if estimation.role == Role.MAFIA :
                            player: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
                            if player == data.speaker or player.info.isHuman :
                                continue
                            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, data.speaker.info, 'He pointed me of being the mafia, but I am not.')
                            return ResponseContent(player, strategy=strategy)

        return None

    # 신뢰도가 높은 플레이어가 마피아로 지목됨
    def _getResponseContent_supportCitizen(self, data: DiscussionData) -> ResponseContent :
        if data.strategy == None :
            return None

        for estimation in data.strategy.mafiaEstimations :
            point: float = self.trustRecorder.getTrustPoint(estimation.playerInfo)
            if point > 30.0 and (point / 100.0) > random.random() :
                player: Player = None
                for dPlayer in self.dPlayers :
                    if dPlayer.player != data.speaker and dPlayer.player.info != estimation.playerInfo :
                        player = dPlayer.player
                        break

                if player != None :
                    strategy: Strategy = Strategy(
                        publicRole=player.publicRole,
                        assumptions=[
                            Assumption(
                                estimations=[Estimation(estimation.playerInfo, Role.CITIZEN)],
                                reason=self.trustRecorder.getPositiveTrustReason(estimation.playerInfo, 'You believe that he is a citizen'),
                            )
                        ]
                    )
                    return ResponseContent(player, strategy=strategy)

        return None

    _responseContentGetters: list[Callable[[DiscussionManager, DiscussionData], ResponseContent]] = [
        _getResponseContent_claimePoliceForMafia,
        _getResponseContent_claimePoliceForPolice,
        _getResponseContent_claimeDoctorForDoctor,
        _getResponseContent_iampointed,
        _getResponseContent_thePolicePointedMe,
        _getResponseContent_supportCitizen,
    ]

    def _stopTask(self) :
        if self._normalDiscussionTask != None :
            self._normalDiscussionTask.cancel()
            asyncio.create_task(self._reapTask(self._normalDiscussionTask))
            self._normalDiscussionTask = None

        if self._responseDiscussionTask != None :
            self._responseDiscussionTask.cancel()
            asyncio.create_task(self._reapTask(self._responseDiscussionTask))
            self._responseDiscussionTask = None

    async def _reapTask(self, task: asyncio.Task) :
        try :
            if not task.done():
                await task
        except asyncio.CancelledError :
            pass
        except Exception as e:
            self.logger.logError("[DiscussionManager] Unhandled exception in task", e)
