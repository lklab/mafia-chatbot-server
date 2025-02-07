import random
import asyncio
from typing import Callable
import time

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import Role
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.strategy import Strategy, Assumption, AssumptionType, Estimation
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.chat_data import ChatData
from mafia_chatbot.game.game_logger import GameLogger, TAG
from mafia_chatbot.game.achievements_manager import AchievementsManager

import  mafia_chatbot.utils.utils as utils

class DiscussionManager :
    pass

class DiscussionPlayer :
    def __init__(self, player: Player) :
        self.player: Player = player
        self.discussionCount: int = 0

    def addDiscussionCount(self) :
        self.discussionCount += 1

class SpeakerStrategy :
    def __init__(self, speaker: Player, strategy: Strategy) :
        self.speaker = speaker
        self.strategy = strategy

class RespondentStrategy :
    def __init__(self, dPlayer: DiscussionPlayer, strategy: Strategy) :
        self.respondent = dPlayer.player
        self.dPlayer = dPlayer
        self.strategy = strategy

class DiscussionContext :
    def __init__(self) :
        self.history: list[tuple[Player, ChatData, Strategy]] = []
        self.lastDiscussuinTime: float = time.monotonic()

    def addDiscussion(self, player: Player, chat: ChatData, strategy: Strategy = None) :
        self.history.append((player, chat, strategy))
        self.lastDiscussuinTime: float = time.monotonic()

    def getLength(self) -> int :
        return len(self.history)

    def getLastSpeaker(self) -> Player :
        return self.history[-1][0]

    def getLastChat(self) -> ChatData :
        return self.history[-1][1]

    def getLastStrategy(self) -> Strategy :
        return self.history[-1][2]

    def getChatList(self) -> list[str] :
        return list(map(lambda h : f'{h[1].sender.name}: {h[1].content}', self.history))

class DiscussionManager :
    def __init__(self, gameState: GameState, trustRecorder: TrustRecorder, llm: LLM, achievementsManager: AchievementsManager) :
        self.gameState: GameState = gameState
        self.trustRecorder: TrustRecorder = trustRecorder
        self.llm: LLM = llm
        self.achievementsManager = achievementsManager
        self.logger: GameLogger = gameState.logger

        self._isRunning: bool = False
        self._mainLogicTask: asyncio.Task = None
        self._responseLogicTasks: list[asyncio.Task] = []
        self._humanChatLogicTasks: list[asyncio.Task] = []

        self.gameState.setOnHumanChatListener(self._onHumanChat)

    def start(self) :
        self.logger.log(TAG.DISCUSSION, 'start discussion')

        # initialize variables
        self._isRunning = True
        self._allDiscussionCount: int = 0

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
        if self.gameState.localPlayer != None :
            asyncio.create_task(self._processLocalPlayer())

        # start main logic
        self._mainLogicTask: asyncio.Task = asyncio.create_task(self._mainLogic())

    async def stop(self) :
        self.logger.log(TAG.DISCUSSION, 'stop discussion')

        self.gameState.setOnHumanChatListener(None)
        self._stopTask()
        self._isRunning = False

        # wait for human message processing
        for task in self._humanChatLogicTasks :
            try :
                if not task.done() :
                    self.logger.log(TAG.DISCUSSION, 'wait for human message processing ...')
                    await task
            except asyncio.CancelledError :
                pass
            except Exception as e:
                self.logger.logError("[DiscussionManager] Unhandled exception in humanChatLogicTask", e)
            except :
                pass

        self.logger.log(TAG.DISCUSSION, 'stop discussion completed')

    async def _mainLogic(self) :
        while self._isRunning :
            # wait for discussion time
            waitTime: float = random.uniform(5.0, 10.0)
            await asyncio.sleep(waitTime)
            if not self._isRunning :
                return

            # update trust records for evaluate strategy
            self.trustRecorder.updateTrustRecords()

            limit: int = 10
            while limit > 0 :
                limit -= 1

                # select player
                dPlayer: DiscussionPlayer = self.dPlayers[0]
                self._addDiscussionCount(dPlayer)

                # get player's past strategy
                pastStrategy: Strategy = dPlayer.player.getDiscussionStrategy(self.gameState.round)

                # evaluate strategy
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, dPlayer.player)

                # check strategy is changed
                if (
                    limit > 0 and # 제한을 초과하지 않음
                    not strategy.isDefaultReasonIncluded() and # 전략에 default reason이 포함되지 않음
                    pastStrategy != None and # 현재 라운드에 이전 전략이 이미 존재
                    strategy == pastStrategy # 현재 라운드의 이전 전략과 동일
                ) :
                    self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}\'s strategy is same, skip(limit={limit}). before={pastStrategy}, after={strategy}')
                else :
                    break

            # generate discussion
            if self.gameState.gameInfo.useLLM :
                discussion: str = await self.llm.getDiscussion(dPlayer.player, strategy)
                if not self._isRunning :
                    return
                discussion = discussion.removeprefix(f'{dPlayer.player.info.name}: ')
            else :
                discussion: str = str(strategy)

            # save data
            dPlayer.player.setDiscussionStrategy(self.gameState.round, strategy)
            self.trustRecorder.discussionStrategyUpdated(dPlayer.player.info, strategy)
            self.achievementsManager.onStrategyUpdated(dPlayer.player, strategy)
            chat: ChatData = self.gameState.appendDiscussionChat(dPlayer.player.info, discussion)

            # response
            self._startResponseThread(dPlayer.player, chat, strategy)

    def _startResponseThread(self, speaker: Player, chat: ChatData, strategy: Strategy = None) :
        context: DiscussionContext = DiscussionContext()
        context.addDiscussion(speaker, chat, strategy)

        self._processNextResponse(context)

    def _processNextResponse(self, context: DiscussionContext) :
        if not self._isRunning :
            return

        speaker: Player = context.getLastSpeaker()
        strategy: Strategy = context.getLastStrategy()

        if strategy != None :
            speakerStrategy: SpeakerStrategy = SpeakerStrategy(speaker, strategy)
            for getter in DiscussionManager._respondentStrategyGetters :
                respondentStrategy = getter(self, speakerStrategy)
                if respondentStrategy != None :
                    task: asyncio.Task = asyncio.create_task(self._responseStrategyLogic(context, respondentStrategy))
                    self._responseLogicTasks.append(task)
                    return

        historyTerm: float = 1.0 / context.getLength()
        willResponse: bool = strategy == None and historyTerm > random.random()
        if strategy != None :
            willResponse = 0.2 * historyTerm > random.random()

        if willResponse :
            task: asyncio.Task = asyncio.create_task(self._responseNormalLogic(context))
            self._responseLogicTasks.append(task)
            return

    async def _responseStrategyLogic(self, context: DiscussionContext, respondentStrategy: RespondentStrategy) :
        respondent: Player = respondentStrategy.respondent
        strategy: Strategy = respondentStrategy.strategy
        self._addDiscussionCount(respondentStrategy.dPlayer)

        # generate discussion
        if self.gameState.gameInfo.useLLM :
            discussion: str = await self.llm.getDiscussion(respondent, strategy)
            if not self._isRunning :
                return
            discussion = discussion.removeprefix(f'{respondent.info.name}: ')
        else :
            discussion: str = str(strategy)

        # wait
        speakTime: float = context.lastDiscussuinTime + random.uniform(5.0, 10.0)
        if speakTime > time.monotonic() :
            await asyncio.sleep(speakTime - time.monotonic())
            if not self._isRunning :
                return

        # save data
        respondent.setDiscussionStrategy(self.gameState.round, strategy)
        self.trustRecorder.discussionStrategyUpdated(respondent.info, strategy)
        self.achievementsManager.onStrategyUpdated(respondent, strategy)
        chat: ChatData = self.gameState.appendDiscussionChat(respondent.info, discussion)
        context.addDiscussion(respondent, chat, strategy)

        # process next response
        self._processNextResponse(context)

    async def _responseNormalLogic(self, context: DiscussionContext) :
        if not self.gameState.gameInfo.useLLM :
            return

        if context.getLength() == 1 :
            # chat을 마지막으로 하는 대화 내역 가져오기
            conversation: list[str] = self.gameState.getDiscussionChatLogs(5, lastChat=context.getLastChat())
        else :
            conversation: list[str] = context.getChatList()

        # 응답 생성하기
        respondent, response = await self.llm.generateResponse(context.getLastSpeaker(), conversation)
        if respondent == None or not self._isRunning :
            return

        # wait
        speakTime: float = context.lastDiscussuinTime + random.uniform(5.0, 10.0)
        if speakTime > time.monotonic() :
            await asyncio.sleep(speakTime - time.monotonic())
            if not self._isRunning :
                return

        # save data
        self._addDiscussionCount(self.dPlayersByPlayer[respondent])
        chat: ChatData = self.gameState.appendDiscussionChat(respondent.info, response)
        context.addDiscussion(respondent, chat)

        # process next response
        self._processNextResponse(context)

    def _onHumanChat(self, chat: ChatData) :
        # check state
        if not self._isRunning :
            return

        # process discussion
        player: Player = self.gameState.getPlayerByInfo(chat.sender)
        self._humanChatLogicTasks.append(asyncio.create_task(self._humanChatLogic(player, chat)))

    async def _humanChatLogic(self, speaker: Player, chat: ChatData) :
        if self.gameState.gameInfo.useLLM :
            # 질문인 경우 바로 응답 메시지 생성
            isQuestion: bool = await self.llm.isMessageQuestion(chat.content)
            if isQuestion :
                self._startResponseThread(speaker, chat)
                return

            # 사용자의 메시지 분석
            strategy: Strategy = await self.llm.analyzeHumanMessage(speaker, chat.content)
            self.logger.log(TAG.DISCUSSION, f'{speaker.info.name}: analyzeHumanMessage result: {strategy}')

            # 유효한 전략일 경우
            if strategy != None and strategy.isEffective() :
                # save data
                speaker.setDiscussionStrategy(self.gameState.round, strategy)
                self.trustRecorder.discussionStrategyUpdated(speaker.info, strategy)
                self.achievementsManager.onStrategyUpdated(speaker, strategy)

                # response
                self._startResponseThread(speaker, chat, strategy)

            # 유효하지 않은 전략일 경우
            else :
                self._startResponseThread(speaker, chat)

        else :
            target: Player = self.gameState.getPlayerByName(chat.content)
            if target == None :
                return None
            strategy: Strategy = evaluator.getOneTargetStrategy(speaker.publicRole, target.info, '')
            self.logger.log(TAG.DISCUSSION, f'{speaker.info.name}: strategy is {strategy}')
            self._startResponseThread(speaker, chat, strategy)

    def _addDiscussionCount(self, dPlayer: DiscussionPlayer) :
        self._allDiscussionCount += 1
        dPlayer.addDiscussionCount()
        self.dPlayers.remove(dPlayer)

        power: float = dPlayer.player.positiveness * self._allDiscussionCount / (dPlayer.discussionCount * (len(self.dPlayers) + 1))
        power = min(power, 1.0)
        index: int = round(pow(random.random(), power) * len(self.dPlayers))
        self.dPlayers.insert(index, dPlayer)

    async def _processLocalPlayer(self) :
        player: Player = self.gameState.localPlayer

        while self._isRunning :
            discussion: str = await utils.getCuiInputAsync('Enter your discussion: ')
            chat: ChatData = self.gameState.appendDiscussionChat(player.info, discussion)
            await self._humanChatLogic(player, chat)

    # 마피아 플레이어의 경찰 주장
    def _getRespondentStrategy_claimePoliceForMafia(self, data: SpeakerStrategy) -> RespondentStrategy :
        if data.speaker.publicRole == Role.POLICE :
            for dPlayer in self.dPlayers :
                if dPlayer.player == data.speaker :
                    continue
                if dPlayer.player.publicRole == Role.CITIZEN and dPlayer.player.info.role == Role.MAFIA :
                    strategy: Strategy = evaluator.claimePoliceForMafiaResponse(self.gameState, self.trustRecorder, dPlayer.player)
                    if strategy != None :
                        self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: claimePoliceForMafia {strategy}')
                        return RespondentStrategy(dPlayer, strategy)

        return None

    # 경찰 플레이어의 경찰 주장
    def _getRespondentStrategy_claimePoliceForPolice(self, data: SpeakerStrategy) -> RespondentStrategy :
        if data.speaker.publicRole == Role.POLICE :
            police: Player = self.gameState.policePlayer
            if not police.info.isHuman and police.isLive and police.publicRole == Role.CITIZEN :
                strategy: Strategy = evaluator.claimePoliceForPoliceResponse(self.gameState, self.trustRecorder, police)
                if strategy != None :
                    self.logger.log(TAG.DISCUSSION, f'{police.info.name}: claimePoliceForPolice {strategy}')
                    return RespondentStrategy(self.dPlayersByPlayer[police], strategy)

        return None

    # 의사 플레이어의 의사 주장
    def _getRespondentStrategy_claimeDoctorForDoctor(self, data: SpeakerStrategy) -> RespondentStrategy :
        doctor: Player = self.gameState.doctorPlayer
        if not doctor.info.isHuman and doctor.isLive and doctor.publicRole == Role.CITIZEN :
            strategy: Strategy = evaluator.claimeDoctorForDoctorResponse(self.gameState, self.trustRecorder, doctor)
            if strategy != None :
                self.logger.log(TAG.DISCUSSION, f'{doctor.info.name}: claimeDoctorForDoctor {strategy}')
                return RespondentStrategy(self.dPlayersByPlayer[doctor], strategy)

        return None

    # 경찰이 나를 지목함
    def _getRespondentStrategy_thePolicePointedMe(self, data: SpeakerStrategy) -> RespondentStrategy :
        if data.speaker.publicRole == Role.POLICE :
            for assumption in data.strategy.assumptions :
                if assumption.assumptionType == AssumptionType.TEST_RESULT :
                    for estimation in assumption.estimations :
                        if estimation.role == Role.MAFIA :
                            player: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
                            if player == data.speaker or player.info.isHuman :
                                continue
                            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, data.speaker.info, 'He pointed me of being the mafia, but I am not.')
                            self.logger.log(TAG.DISCUSSION, f'{player.info.name}: thePolicePointedMe {strategy}')
                            return RespondentStrategy(self.dPlayersByPlayer[player], strategy)

        return None

    # 내가 지목당함
    def _getRespondentStrategy_iampointed(self, data: SpeakerStrategy) -> RespondentStrategy :
        for estimation in data.strategy.mafiaEstimations :
            player: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)

            # 이번 라운드에 토론하지 않았을 경우
            if player == data.speaker or player.info.isHuman or player.getDiscussionStrategy(self.gameState.round) != None :
                continue

            # 나를 지목하는 플레이어 수에 따라 일정 확률로 발언함
            pointerCount: int = len(self.trustRecorder.getPointerOrVoters(player.info))
            ratio: float = pointerCount / (self.gameState.getPlayerCount() - 1)
            if ratio > random.random() :
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, player)
                self.logger.log(TAG.DISCUSSION, f'{player.info.name}: iampointed {strategy}')
                return RespondentStrategy(self.dPlayersByPlayer[player], strategy)

        return None

    # 신뢰도가 높은 플레이어가 마피아로 지목됨
    def _getRespondentStrategy_supportCitizen(self, data: SpeakerStrategy) -> RespondentStrategy :
        for estimation in data.strategy.mafiaEstimations :
            point: float = self.trustRecorder.getTrustPoint(estimation.playerInfo)
            if point > 30.0 and (point / 100.0) > random.random() :
                respondentDPlayer: DiscussionPlayer = None
                for dPlayer in self.dPlayers : # AI 사용자 및 발언 우선순위로 선택해야 하므로 gameState.players 대신 dPlayers 사용
                    if dPlayer.player != data.speaker and dPlayer.player.info != estimation.playerInfo :
                        respondentDPlayer = dPlayer
                        break

                if respondentDPlayer != None :
                    strategy: Strategy = Strategy(
                        publicRole=respondentDPlayer.player.publicRole,
                        assumptions=[
                            Assumption(
                                estimations=[Estimation(estimation.playerInfo, Role.CITIZEN)],
                                reason=self.trustRecorder.getPositiveTrustReason(estimation.playerInfo, 'You believe that he is not a mafia'),
                            )
                        ]
                    )
                    self.logger.log(TAG.DISCUSSION, f'{respondentDPlayer.player.info.name}: supportCitizen {strategy}')
                    return RespondentStrategy(respondentDPlayer, strategy)

        return None

    _respondentStrategyGetters: list[Callable[[DiscussionManager, SpeakerStrategy], RespondentStrategy]] = [
        _getRespondentStrategy_claimePoliceForMafia,
        _getRespondentStrategy_claimePoliceForPolice,
        _getRespondentStrategy_claimeDoctorForDoctor,
        _getRespondentStrategy_thePolicePointedMe,
        _getRespondentStrategy_iampointed,
        _getRespondentStrategy_supportCitizen,
    ]

    def _stopTask(self) :
        if self._mainLogicTask != None :
            self._mainLogicTask.cancel()
            asyncio.create_task(self._reapTask(self._mainLogicTask))
            self._mainLogicTask = None

        for task in self._responseLogicTasks :
            task.cancel()
            asyncio.create_task(self._reapTask(task))
        self._responseLogicTasks.clear()

    async def _reapTask(self, task: asyncio.Task) :
        try :
            if not task.done() :
                await task
        except asyncio.CancelledError :
            pass
        except Exception as e:
            self.logger.logError("[DiscussionManager] Unhandled exception in task", e)
