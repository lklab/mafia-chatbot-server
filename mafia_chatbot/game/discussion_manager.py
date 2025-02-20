import random
import asyncio
from typing import Callable

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
from mafia_chatbot.game.discussion_player import DiscussionPlayer, Discussion, DiscussionTicket, DiscussionContext, CONVERSATION_WINDOW

class DiscussionManager :
    def __init__(self, gameState: GameState, trustRecorder: TrustRecorder, llm: LLM, achievementsManager: AchievementsManager) :
        self.gameState: GameState = gameState
        self.trustRecorder: TrustRecorder = trustRecorder
        self.llm: LLM = llm
        self.achievementsManager = achievementsManager
        self.logger: GameLogger = gameState.logger

        self.isRunning: bool = False
        self.generateResponseTasks: list[asyncio.Task] = []
        self.humanChatLogicTasks: list[asyncio.Task] = []

        # setup discussion players
        players: list[Player] = list(filter(lambda p: not p.info.isHuman, self.gameState.players))
        self.dPlayers: list[DiscussionPlayer] = []
        self.dPlayerDict: dict[Player, DiscussionPlayer] = {}
        for player in players :
            dPlayer: DiscussionPlayer = DiscussionPlayer(
                player=player,
                gameState=self.gameState,
                trustRecorder=self.trustRecorder,
                llm=self.llm,
                onDiscussion=self._onDiscussion,
            )
            self.dPlayers.append(dPlayer)
            self.dPlayerDict[player] = dPlayer

    def start(self) :
        self.logger.log(TAG.DISCUSSION, 'start discussion')

        # initialize variables
        self.isRunning = True

        # start discussion players
        for dPlayer in self.dPlayers :
            dPlayer.start()

        # set human chat listener
        self.gameState.setOnHumanChatListener(self._onHumanChat)

    async def stop(self) :
        self.logger.log(TAG.DISCUSSION, 'stop discussion')

        self.isRunning = False
        self.gameState.setOnHumanChatListener(None)
        self._stopTask()

        # stop discussion players
        for dPlayer in self.dPlayers :
            dPlayer.stop()

        # wait for human message processing
        for task in self.humanChatLogicTasks :
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

    def _onDiscussion(self, discussion: Discussion) :
        if not self.isRunning :
            return

        if discussion.strategy != None :
            discussion.player.setDiscussionStrategy(self.gameState.round, discussion.strategy)
            self.trustRecorder.discussionStrategyUpdated(discussion.player.info, discussion.strategy)
            self.achievementsManager.onStrategyUpdated(discussion.player, discussion.strategy)

        chat: ChatData = self.gameState.appendDiscussionChat(discussion.player.info, discussion.text)
        discussion.context.addDiscussion(chat)

        task = asyncio.create_task(self._generateResponse(discussion))
        self.generateResponseTasks.append(task)

    def _onHumanChat(self, chat: ChatData) :
        # check state
        if not self.isRunning :
            return

        # process chat
        player: Player = self.gameState.getPlayerByInfo(chat.sender)
        task = asyncio.create_task(self._processHumanChat(player, chat))
        self.humanChatLogicTasks.append(task)

    async def _processHumanChat(self, player: Player, chat: ChatData) :
        discussion: Discussion = Discussion(
            player=player,
            text=chat.content,
            context=DiscussionContext(),
        )
        discussion.context.addDiscussion(chat)

        if self.gameState.gameInfo.useLLM :
            # 질문인 경우
            isQuestion: bool = await self.llm.isMessageQuestion(chat.content)
            if isQuestion :
                discussion.isQuestion = True
                await self._generateResponse(discussion)
                return

            # 사용자의 메시지 분석
            strategy: Strategy = await self.llm.analyzeHumanMessage(player, chat.content)
            self.logger.log(TAG.DISCUSSION, f'{player.info.name}: analyzeHumanMessage result: {strategy}')

            # 유효한 전략일 경우
            if strategy != None and strategy.isEffective() :
                # save data
                player.setDiscussionStrategy(self.gameState.round, strategy)
                self.trustRecorder.discussionStrategyUpdated(player.info, strategy)
                self.achievementsManager.onStrategyUpdated(player, strategy)

                # response
                discussion.strategy = strategy
                await self._generateResponse(discussion)

            # 유효하지 않은 전략일 경우
            else :
                await self._generateResponse(discussion)

        else :
            target: Player = self.gameState.getPlayerByName(chat.content)
            if target == None :
                return
            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, target.info, '')
            self.logger.log(TAG.DISCUSSION, f'{player.info.name}: strategy is {strategy}')
            discussion.strategy = strategy
            await self._generateResponse(discussion)

    async def _generateResponse(self, discussion: Discussion) :
        if not self.isRunning :
            return

        if discussion.strategy != None :
            for getter in DiscussionManager._discussionTicketGetters :
                ticket: DiscussionTicket = getter(self, discussion)
                if ticket != None :
                    self._forwardTicket(ticket)
                    return

        if not self.gameState.gameInfo.useLLM :
            return

        historyTerm: float = 1.0 / discussion.context.getLength()
        willResponse: bool = discussion.isQuestion or (discussion.strategy == None and historyTerm > random.random())
        if not willResponse :
            willResponse = 0.2 * historyTerm > random.random()

        if willResponse :
            # 응답자 가져오기
            receiver: Player = None
            if discussion.receiver != None :
                receiver = discussion.receiver
            else :
                conversation: list[str] = discussion.context.getChatLog(self.gameState, CONVERSATION_WINDOW) # 채팅 로그 가져오기
                receiver = await self.llm.getRespondent(discussion.player, conversation)

            if receiver == None or receiver.info.isHuman or receiver == discussion.player or not self.isRunning :
                return

            # 티켓 발행
            ticket: DiscussionTicket = DiscussionTicket(
                sender=discussion.player,
                receiver=receiver,
                context=discussion.context,
                chat=discussion.context.getLastChat(),
            )
            self._forwardTicket(ticket)

    def _forwardTicket(self, ticket: DiscussionTicket) :
        dPlayer: DiscussionPlayer = self.dPlayerDict.get(ticket.receiver)
        if dPlayer != None :
            dPlayer.forwardTicket(ticket)

    # 마피아 플레이어의 경찰 주장
    def _getDiscussionTicket_claimePoliceForMafia(self, discussion: Discussion) -> DiscussionTicket :
        if discussion.player.publicRole == Role.POLICE :
            for dPlayer in self.dPlayers :
                if dPlayer.player == discussion.player :
                    continue
                if dPlayer.player.publicRole == Role.CITIZEN and dPlayer.player.info.role == Role.MAFIA :
                    strategy: Strategy = evaluator.claimePoliceForMafiaResponse(self.gameState, self.trustRecorder, dPlayer.player)
                    if strategy != None :
                        self.logger.log(TAG.DISCUSSION, f'{dPlayer.player.info.name}: claimePoliceForMafia {strategy}')
                        return DiscussionTicket(
                            sender=discussion.player,
                            receiver=dPlayer.player,
                            context=discussion.context,
                            strategy=strategy,
                        )

        return None

    # 경찰 플레이어의 경찰 주장
    def _getDiscussionTicket_claimePoliceForPolice(self, discussion: Discussion) -> DiscussionTicket :
        if discussion.player.publicRole == Role.POLICE :
            police: Player = self.gameState.policePlayer
            if not police.info.isHuman and police.isLive and police.publicRole == Role.CITIZEN :
                strategy: Strategy = evaluator.claimePoliceForPoliceResponse(self.gameState, self.trustRecorder, police)
                if strategy != None :
                    self.logger.log(TAG.DISCUSSION, f'{police.info.name}: claimePoliceForPolice {strategy}')
                    return DiscussionTicket(
                        sender=discussion.player,
                        receiver=police,
                        context=discussion.context,
                        strategy=strategy,
                    )

        return None

    # 의사 플레이어의 의사 주장
    def _getDiscussionTicket_claimeDoctorForDoctor(self, discussion: Discussion) -> DiscussionTicket :
        doctor: Player = self.gameState.doctorPlayer
        if not doctor.info.isHuman and doctor.isLive and doctor.publicRole == Role.CITIZEN :
            strategy: Strategy = evaluator.claimeDoctorForDoctorResponse(self.gameState, self.trustRecorder, doctor)
            if strategy != None :
                self.logger.log(TAG.DISCUSSION, f'{doctor.info.name}: claimeDoctorForDoctor {strategy}')
                return DiscussionTicket(
                    sender=discussion.player,
                    receiver=doctor,
                    context=discussion.context,
                    strategy=strategy,
                )

        return None

    # 경찰이 나를 지목함
    def _getDiscussionTicket_thePolicePointedMe(self, discussion: Discussion) -> DiscussionTicket :
        if discussion.player.publicRole == Role.POLICE :
            for assumption in discussion.strategy.assumptions :
                if assumption.assumptionType == AssumptionType.TEST_RESULT :
                    for estimation in assumption.estimations :
                        if estimation.role == Role.MAFIA :
                            player: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
                            if player == discussion.player or player.info.isHuman :
                                continue
                            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, discussion.player.info, 'He pointed me of being the mafia, but I am not.')
                            self.logger.log(TAG.DISCUSSION, f'{player.info.name}: thePolicePointedMe {strategy}')
                            return DiscussionTicket(
                                sender=discussion.player,
                                receiver=player,
                                context=discussion.context,
                                strategy=strategy,
                            )

        return None

    # 내가 지목당함
    def _getDiscussionTicket_iampointed(self, discussion: Discussion) -> DiscussionTicket :
        for estimation in discussion.strategy.mafiaEstimations :
            player: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)

            # 이번 라운드에 토론하지 않았을 경우
            if player == discussion.player or player.info.isHuman or player.getDiscussionStrategy(self.gameState.round) != None :
                continue

            # 나를 지목하는 플레이어 수에 따라 일정 확률로 발언함
            pointerCount: int = len(self.trustRecorder.getPointerOrVoters(player.info))
            ratio: float = pointerCount / (self.gameState.getPlayerCount() - 1)
            if ratio > random.random() :
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, player)
                if strategy != None :
                    self.logger.log(TAG.DISCUSSION, f'{player.info.name}: iampointed {strategy}')
                    return DiscussionTicket(
                        sender=discussion.player,
                        receiver=player,
                        context=discussion.context,
                        strategy=strategy,
                    )

        return None

    # 신뢰도가 높은 플레이어가 마피아로 지목됨
    def _getDiscussionTicket_supportCitizen(self, discussion: Discussion) -> DiscussionTicket :
        for estimation in discussion.strategy.mafiaEstimations :
            point: float = self.trustRecorder.getTrustPoint(estimation.playerInfo)
            if point > 30.0 and (point / 100.0) > random.random() :
                respondentDPlayer: DiscussionPlayer = None
                for dPlayer in self.dPlayers : # AI 사용자 및 발언 우선순위로 선택해야 하므로 gameState.players 대신 dPlayers 사용
                    if dPlayer.player != discussion.player and dPlayer.player.info != estimation.playerInfo :
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
                    return DiscussionTicket(
                        sender=discussion.player,
                        receiver=respondentDPlayer.player,
                        context=discussion.context,
                        strategy=strategy,
                    )

        return None

    _discussionTicketGetters: list[Callable[["DiscussionManager", Discussion], DiscussionTicket]] = [
        _getDiscussionTicket_claimePoliceForMafia,
        _getDiscussionTicket_claimePoliceForPolice,
        _getDiscussionTicket_claimeDoctorForDoctor,
        _getDiscussionTicket_thePolicePointedMe,
        _getDiscussionTicket_iampointed,
        _getDiscussionTicket_supportCitizen,
    ]

    def _stopTask(self) :
        for task in self.generateResponseTasks :
            task.cancel()
            asyncio.create_task(self._reapTask(task))
        self.generateResponseTasks.clear()

    async def _reapTask(self, task: asyncio.Task) :
        try :
            if not task.done() :
                await task
        except asyncio.CancelledError :
            pass
        except Exception as e:
            self.logger.logError("[DiscussionManager] Unhandled exception in task", e)
        except :
            pass
