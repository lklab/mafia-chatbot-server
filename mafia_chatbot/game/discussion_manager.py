import random
import asyncio
from datetime import datetime, timedelta

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.player import Player
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.strategy import Strategy
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.chat_data import ChatData
from mafia_chatbot.game.game_logger import GameLogger

import  mafia_chatbot.utils.utils as utils

class DiscussionPlayer :
    def __init__(self, player: Player) :
        self.player: Player = player
        self.discussionCount: int = 0

    def addDiscussionCount(self) :
        self.discussionCount += 1

class DiscussionManager :
    def __init__(self, gameState: GameState, trustRecorder: TrustRecorder, llm: LLM, logger: GameLogger) :
        self.gameState = gameState
        self.trustRecorder = trustRecorder
        self.llm = llm
        self.logger = logger

        self._isRunning: bool = False
        self._currentTask: asyncio.Task = None

        self.gameState.setOnHumanChatListener(self._onHumanChat)

    def start(self) :
        # initialize variables
        self._isRunning = True
        self._allDiscussionCount: int = 0
        self._lastDiscussionTime: datetime = datetime.now()
        self._processingHumanDiscussionCount: int = 0

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

        # process local player
        asyncio.create_task(self._processLocalPlayer())

        # generate first discussion
        self._generateNormalDiscussion()

    async def stop(self) :
        self._stopTask()
        self._isRunning = False

        await utils.waitUntil(self._isNotProcessingHumanDiscussion)

    def _generateDiscussion(self) :
        self._generateNormalDiscussion()

    def _generateNormalDiscussion(self) :
        self._stopTask()

        # select player
        dPlayer: DiscussionPlayer = self.dPlayers[0]

        # decide discussion time
        discussionTime: datetime = self._lastDiscussionTime + timedelta(seconds=random.uniform(2.0, 5.0))

        # start task
        self._currentTask = asyncio.create_task(self._generateNormalDiscussionTask(dPlayer, discussionTime))

    async def _generateNormalDiscussionTask(self, dPlayer: DiscussionPlayer, discussionTime: datetime) :
        # wait for discussion time
        waitTime: float = (discussionTime - datetime.now()).total_seconds()
        await asyncio.sleep(waitTime)

        # check state
        if not self._isRunning :
            return

        # evaluate strategy
        self.trustRecorder.updateTrustRecords()
        strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, dPlayer.player)

        # generate discussion
        if self.gameState.gameInfo.useLLM :
            discussion: str = self.llm.getDiscussion(self.gameState, dPlayer.player, strategy) # TODO await LLM
        else :
            discussion: str = str(strategy)

        # check state
        if not self._isRunning :
            return

        # set last discussion time
        self._lastDiscussionTime = discussionTime

        # apply strategy and discussion
        dPlayer.player.setDiscussionStrategy(self.gameState.round, strategy)

        # record trust info
        self.trustRecorder.discussionStrategyUpdated(dPlayer.player.info, strategy)

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

        # generate next discussion
        self._generateDiscussion()

    async def _processLocalPlayer(self) :
        if self.gameState.localPlayer != None :
            player: Player = self.gameState.localPlayer

            while True :
                discussion: str = await utils.getCuiInputAsync('Enter your discussion: ')

                # check state
                if not self._isRunning :
                    return

                # process discussion
                if self._processHumanDiscussion(player, discussion) :
                    break

    def _onHumanChat(self, chat: ChatData) :
        # check state
        if not self._isRunning :
            return

        # process discussion
        player: Player = self.gameState.getPlayerByInfo(chat.sender)
        self._processHumanDiscussion(player, chat.content)

    def _processHumanDiscussion(self, player: Player, discussion: str) -> bool :
        if self.gameState.gameInfo.useLLM :
            self._processingHumanDiscussionCount += 1
            strategy: Strategy = self.llm.analyzeHumanMessage(player, discussion) # TODO await
            self._processingHumanDiscussionCount -= 1
            self.logger.log(f'human {player.info.name}\'s strategy: {strategy}')
        else :
            target: Player = self.gameState.getPlayerByName(discussion)
            if target == None :
                return False
            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, target.info, '')

        # apply strategy and discussion
        player.setDiscussionStrategy(self.gameState.round, strategy)

        # record trust info
        self.trustRecorder.discussionStrategyUpdated(player.info, strategy)

        # add chat
        if player.info.isLocalPlayer :
            self.gameState.appendDiscussionChat(player.info, f'I think {strategy.mainTarget.name} is a mafia')

        # generate next discussion
        self._generateDiscussion()

        return True

    def _isNotProcessingHumanDiscussion(self) -> bool :
        return self._processingHumanDiscussionCount == 0

    def _stopTask(self) :
        if self._currentTask != None :
            self._currentTask.cancel()
            asyncio.create_task(self._reapTask(self._currentTask))
            self._currentTask = None

    async def _reapTask(self, task: asyncio.Task) :
        try :
            if not task.done():
                await task
        except asyncio.CancelledError :
            pass
        except Exception as e:
            print(f"[DiscussionManager] Unhandled exception in task: {e}")
