import asyncio
from typing import Callable, Deque
from dataclasses import dataclass
import random
import time
from collections import deque

from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import Role
from mafia_chatbot.game.strategy import Strategy
from mafia_chatbot.game.chat_data import ChatData
from mafia_chatbot.game.game_state import GameState
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.llm import LLM

class DiscussionContext :
    def __init__(self) :
        self.history: list[tuple[Player, ChatData, Strategy]] = []

    def addDiscussion(self, player: Player, chat: ChatData, strategy: Strategy = None) :
        self.history.append((player, chat, strategy))

    def getLength(self) -> int :
        return len(self.history)

    def getLastChat(self) -> ChatData :
        return self.history[-1][1]

    def getChatList(self) -> list[str] :
        return list(map(lambda h : f'{h[1].sender.name}: {h[1].content}', self.history))

@dataclass
class Discussion :
    player: Player
    text: str
    context: DiscussionContext
    isQuestion: bool = False
    strategy: Strategy = None
    receiver: Player = None # TODO receiver가 인간일 수도 있음

@dataclass
class DiscussionTicket :
    sender: Player
    context: DiscussionContext
    strategy: Strategy = None
    chat: ChatData = None

class DiscussionPlayer :
    def __init__(self,
            player: Player,
            gameState: GameState,
            trustRecorder: TrustRecorder,
            llm: LLM,
            onDiscussion: Callable[[Discussion], None],
    ) :
        self.player = player
        self.gameState = gameState
        self.logger = gameState.logger
        self.trustRecorder = trustRecorder
        self.llm = llm
        self.onDiscussion = onDiscussion

        self.mainTask: asyncio.Task = None
        self.waitTask: asyncio.Task = None
        self.isRunning: bool = False
        self.startTime: float = 0
        self.myDiscussionCount: int = 0
        self.ticketQueue: Deque[DiscussionTicket] = deque()

    def start(self) :
        if self.mainTask == None :
            self.isRunning = True
            self.startTime = time.monotonic()
            self.mainTask = asyncio.create_task(self._mainTask())

    def stop(self) :
        self.isRunning = False
        self._stopTask()

    def forwardTicket(self, ticket: DiscussionTicket) :
        self.ticketQueue.append(ticket)
        if self.waitTask != None :
            self.waitTask.cancel()
            self.waitTask = None

    async def _mainTask(self) :
        # 자신이 공개된 경찰일 경우 라운드 시작 후 짧은 시간 이내에 직전 조사 결과 발표
        if self.player.publicRole == Role.POLICE :
            strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, self.player)
            if strategy != None :
                await self._issueDiscussionFromStrategy(strategy, random.uniform(3.0, 5.0))

        # 메인 로직
        while self.isRunning :
            if len(self.ticketQueue) > 0 :
                ticket: DiscussionTicket = self.ticketQueue.popleft()
                await self._issueResponse(ticket)
                continue

            waitMax: float = 30.0
            waitMin: float = 30.0 - 23.0 / (self.myDiscussionCount + 1) # 7.0 ~ 30.0
            self.waitTask = asyncio.create_task(self._issueDiscussion(random.uniform(waitMin, waitMax)))
            try :
                await self.waitTask
            except asyncio.CancelledError :
                pass
            self.waitTask = None

    async def _issueDiscussionFromStrategy(self, strategy: Strategy, delay: float) :
        speakTime: float = time.monotonic() + delay

        if self.gameState.gameInfo.useLLM :
            text = await self.llm.getDiscussion(self.player, strategy)
            text = text.removeprefix(f'{self.player.info.name}: ')
        else :
            text: str = str(strategy)

        if not self.isRunning :
            return
        if speakTime > time.monotonic() :
            await asyncio.sleep(speakTime - time.monotonic())
            if not self.isRunning :
                return

        discussion: Discussion = Discussion(
            player=self.player,
            text=text,
            context=DiscussionContext(),
            strategy=strategy,
        )
        self.myDiscussionCount += 1
        self.onDiscussion(discussion)

    async def _issueDiscussion(self, delay: float) :
        await asyncio.sleep(delay)
        if not self.isRunning :
            return

        text: str = 'None'
        pastStrategy: Strategy = self.player.getDiscussionStrategy(self.gameState.round)
        strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, self.player)
        isQuestion: bool = False
        receiver: Player = None

        chatCount: int = 5

        # 이전 전략과 동일한 경우 None 처리
        if (
            strategy != None
            and not strategy.isDefaultReasonIncluded() # 전략에 default reason이 포함되지 않음
            and strategy == pastStrategy # 현재 라운드의 이전 전략과 동일
        ) :
            strategy = None

        # 최근 n개 대화 내역에 대상의 발언이 있는지 확인
        targetChat: ChatData = None
        if strategy != None :
            chatList = self.gameState.chatList
            for i in range(len(chatList) - 1, max(-1, len(chatList) - 1 - chatCount), -1) :
                if chatList[i].sender == strategy.mainTarget :
                    targetChat = chatList[i]
                    break

        # public role이 바뀌었거나 default reason이 아닌 경우 반드시 전략 발언
        isMustUseStrategy: bool = False
        if strategy != None :
            publicRole, _ = self.player.getChangeRole(strategy.publicRole)
            isPublicRoleChanged: bool = self.player.publicRole != publicRole
            isMustUseStrategy = isPublicRoleChanged or not strategy.isDefaultReasonIncluded()

        if self.gameState.gameInfo.useLLM :
            # public role이 바뀌었거나 default reason이 아닌 경우 반드시 전략 발언
            if isMustUseStrategy :
                text = await self.llm.getDiscussion(self.player, strategy, conversationLogsCount=chatCount)

            # 랜덤으로 선택
            else :
                methods: list[int] = list(range(5))
                weights: list[float] = [5, 2, 1, 1, 0]

                if self.gameState.round > 0 and time.monotonic() - self.startTime < 15.0 :
                    weights[4] = 5 / (self.gameState.getCurrentRoundDiscussionChatCount() + 1)

                if strategy == None :
                    weights[0] = 0
                    weights[1] = 0
                    weights[2] = 0
                elif targetChat == None :
                    weights[0] = 0

                method: int = random.choices(methods, weights=weights, k=1)[0]

                # 대상의 최근 토론을 의심하기
                if method == 0 :
                    strategy.changeDefaultReason(f"Make a plausible argument to suspect {targetChat.sender.name} as the mafia based on their statement: \"{targetChat.content}\".")
                    text = await self.llm.getDiscussion(self.player, strategy, conversationLogsCount=chatCount)

                # strategy 그대로 사용
                elif method == 1 :
                    text = await self.llm.getDiscussion(self.player, strategy, conversationLogsCount=chatCount)

                # 대상에게 질문하기
                elif method == 2 :
                    receiver = self.gameState.getPlayerByInfo(strategy.mainTarget)
                    text = await self.llm.generateQuestion(self.player, receiver, self.gameState.getRecentConversationLogs(chatCount))
                    isQuestion = True

                # 아무 말 하기
                elif method == 3 :
                    text = await self.llm.generateNormalDiscussion(self.player, self.gameState.getRecentConversationLogs(chatCount))

                # 지난 밤에 관한 대화
                else : # elif method == 4 :
                    text = '' # TODO

            text = text.removeprefix(f'{self.player.info.name}: ')

        else :
            if strategy != None :
                text: str = str(strategy)

        if not self.isRunning :
            return

        discussion: Discussion = Discussion(
            player=self.player,
            text=text,
            context=DiscussionContext(),
            isQuestion=isQuestion,
            strategy=strategy,
            receiver=receiver,
        )
        self.myDiscussionCount += 1
        self.onDiscussion(discussion)

    async def _issueResponse(self, ticket: DiscussionTicket) :
        speakTime: float = time.monotonic() + random.uniform(7.0, 10.0)
        discussion: Discussion = None

        if ticket.strategy != None :
            if self.gameState.gameInfo.useLLM :
                text: str = await self.llm.getDiscussion(self.player, ticket.strategy)
                text = text.removeprefix(f'{self.player.info.name}: ')
            else :
                text: str = str(ticket.strategy)

            discussion: Discussion = Discussion(
                player=self.player,
                text=text,
                context=ticket.context,
                strategy=ticket.strategy,
            )

        elif ticket.chat != None :
            if not self.gameState.gameInfo.useLLM :
                return

            if ticket.context.getLength() == 1 :
                # chat을 마지막으로 하는 대화 내역 가져오기
                conversation: list[str] = self.gameState.getDiscussionChatLogs(5, lastChat=ticket.context.getLastChat())
            else :
                conversation: list[str] = ticket.context.getChatList()

            # 응답 생성하기
            text = await self.llm.generateResponse(ticket.sender, conversation) # TODO 응답만 생성하도록 하기

            discussion: Discussion = Discussion(
                player=self.player,
                text=text,
                context=ticket.context,
            )

        if discussion == None or not self.isRunning :
            return
        if speakTime > time.monotonic() :
            await asyncio.sleep(speakTime - time.monotonic())
            if not self.isRunning :
                return

        self.myDiscussionCount += 1
        self.onDiscussion(discussion)

    def _stopTask(self) :
        if self.waitTask != None :
            self.waitTask.cancel()
            self.waitTask = None

        if self.mainTask != None :
            self.mainTask.cancel()
            asyncio.create_task(self._reapTask(self.mainTask))
            self.mainTask = None

    async def _reapTask(self, task: asyncio.Task) :
        try :
            if not task.done() :
                await task
        except asyncio.CancelledError :
            pass
        except Exception as e :
            self.logger.logError("[DiscussionPlayer] Unhandled exception in task", e)
