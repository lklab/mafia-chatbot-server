import random
import asyncio

from mafia_chatbot.game.game_state import GameState, Phase
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.player import Player
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.strategy import Strategy
from mafia_chatbot.game.llm import LLM

class DiscussionPlayer :
    def __init__(self, player: Player) :
        self.player: Player = player
        self.discussionCount: int = 0

    def addDiscussionCount(self) :
        self.discussionCount += 1

class DiscussionManager :
    def __init__(self, gameState: GameState, trustRecorder: TrustRecorder, llm: LLM) :
        self.gameState = gameState
        self.trustRecorder = trustRecorder
        self.llm = llm

        self._currentTask: asyncio.Task = None

    def start(self) :
        # initialize variables
        self.allDiscussionCount: int = 0

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

        # generate first discussion
        self._generateNormalDiscussion()

    def stop(self) :
        self._stopTask()

    def _generateDiscussion(self) :
        pass

    def _generateNormalDiscussion(self) :
        self._stopTask()

        # select player
        dPlayer: DiscussionPlayer = self.dPlayers[0]

        # decide wait time
        waitTime: float = random.uniform(2.0, 5.0)

        # start task
        self._currentTask = asyncio.create_task(self._generateNormalDiscussionTask(dPlayer, waitTime))

    async def _generateNormalDiscussionTask(self, dPlayer: DiscussionPlayer, waitTime: float) :
        await asyncio.sleep(waitTime)

        # check phase
        if self.gameState.currentPhase != Phase.DAY :
            return

        # evaluate strategy
        self.trustRecorder.updateTrustRecords()
        strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, self.trustRecorder, dPlayer.player)

        # generate discussion
        if self.gameState.gameInfo.useLLM :
            discussion: str = self.llm.getDiscussion(self.gameState, dPlayer.player, strategy) # TODO await LLM
        else :
            discussion: str = str(strategy)

        # check phase
        if self.gameState.currentPhase != Phase.DAY :
            return

        # apply strategy and discussion
        dPlayer.player.setDiscussionStrategy(self.gameState.round, strategy)

        # record trust info
        self.trustRecorder.discussionStrategyUpdated(dPlayer.player.info, strategy)

        # add chat
        self.gameState.appendDiscussionChat(dPlayer.player.info, discussion)

        # rearrange player
        self.allDiscussionCount += 1
        dPlayer.addDiscussionCount()
        self.dPlayers.remove(dPlayer)

        power: float = dPlayer.player.positiveness * self.allDiscussionCount / (dPlayer.discussionCount * (len(self.dPlayers) + 1))
        power = min(power, 1.0)
        index: int = round(pow(random.random(), power) * len(self.dPlayers))
        self.dPlayers.insert(index, dPlayer)

        # generate next discussion
        self._generateDiscussion()

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
