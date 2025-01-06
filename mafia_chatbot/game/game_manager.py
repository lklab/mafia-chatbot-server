import asyncio
import time

from mafia_chatbot.game.game_state import *
from mafia_chatbot.game.game_result import *
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.user_message_processor import UserMessageProcessor
from mafia_chatbot.game.game_end_info import GameEndInfo, GameEndReason, gameEndReasonToProtoDict
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.discussion_manager import DiscussionManager
from mafia_chatbot.game.game_logger import TAG

from mafia_chatbot.network.client_user import ClientUser

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.gameState = GameState(gameInfo)
        self.trustRecorder: TrustRecorder = TrustRecorder(self.gameState)
        self.terminated: bool = False

        for player in self.gameState.userPlayers :
            self._subscribeUser(player)

        self.llm = LLM(self.gameState)

        self.discussionManager: DiscussionManager = None

        for player in self.gameState.players :
            self.gameState.logger.log(TAG.INFO, player.getFullRepr())

        self._ = self.gameState.translate

        self.gameEndReason: game_data_pb2.GameEndReason = game_data_pb2.GameEndReason.GAME_END_INTERRUPTED

    def terminate(self, reason=game_data_pb2.GameEndReason.GAME_END_INTERRUPTED) :
        if self.terminated :
            return
        self.terminated = True
        self.gameEndReason = reason

    def sendGameEndToUsers(self) :
        message = game_pb2.GameEnd()
        message.reason = self.gameEndReason
        for player in self.gameState.userPlayers :
            player.user.send(message)
            player.user.clearSubscribers()

    def removeUser(self, user: ClientUser) :
        user.clearSubscribers()
        self.gameState.removeUser(user)

    def _subscribeUser(self, player: Player) :
        UserMessageProcessor(self.gameState, self.trustRecorder, player)

    async def start(self) :
        self.gameState.setPhase(Phase.PREPARE)
        await asyncio.sleep(1)
        await self._mainLogic()

    async def _mainLogic(self) :
        gameEndInfo: GameEndInfo = None

        while True :
            self.gameState.setPhase(Phase.DAY)
            self.trustRecorder.startNewRound()
            await self._processDay()

            self.gameState.setPhase(Phase.EVENING)
            await self._processEvening()

            gameEndInfo = self.checkGameEnd()
            if gameEndInfo :
                break

            self.gameState.setPhase(Phase.NIGHT)
            await self._processNight()

            gameEndInfo = self.checkGameEnd()
            if gameEndInfo :
                break

            self.gameState.addRound()

        self.gameState.setPhase(Phase.END)
        self.terminate(gameEndReasonToProtoDict[gameEndInfo.reason])

    async def _processDay(self) :
        self._addSystemChat(self._("It is now morning. Please begin your discussion."))

        # start discussion
        if len(self.gameState.players) > len(self.gameState.userPlayers) :
            self.discussionManager = DiscussionManager(self.gameState, self.trustRecorder, self.llm)
            self.discussionManager.start()
        else :
            self.discussionManager = None

        # await until time limit
        waitTime: float = self.gameState.timeLimit - time.monotonic()
        await asyncio.sleep(waitTime)

        # stop discussion
        if self.discussionManager != None :
            await self.discussionManager.stop()
            self.discussionManager = None

    async def _processEvening(self) :
        self.trustRecorder.updateTrustRecords()

        # process local player's vote
        cuiInputTask: asyncio.Task = None
        if self.gameState.localPlayer != None and self.gameState.localPlayer.isLive :
            cuiInputTask = asyncio.create_task(self.gameState.getPlayerFromCuiAsync('Choose the player to vote on: '))

        voteData: VoteData = self.gameState.getCurrentVoteData()
        players = self.gameState.players

        # process bot player's vote
        for player in players :
            if not player.info.isHuman :
                asyncio.create_task(self._processPlayerVote(voteData, player))

        # await until time limit
        waitTime: float = self.gameState.timeLimit - time.monotonic()
        await asyncio.sleep(waitTime)

        # get local player's vote
        if cuiInputTask != None :
            targetPlayer: Player = await cuiInputTask
            strategy: VoteStrategy = VoteStrategy(targetPlayer.info)
            voteData.setVoteStrategy(self.gameState.localPlayer, strategy)
            self.trustRecorder.voteStrategyUpdated(self.gameState.localPlayer.info, strategy)

        # evaluate vote data
        voteData.evaluate()
        votingResultsText = self._('Voting results')
        votingResultsList = '\n'.join(voteData.getVoteResultStr())
        self._addSystemChat(f'[{votingResultsText}]\n{votingResultsList}')

        if voteData.isTie :
            self._addSystemChat(self._('No one was executed due to a tie.'))
        else :
            _name = voteData.targetPlayer.name
            _role = self.gameState.translateRole[voteData.targetPlayer.role]
            self._addSystemChat(self._('{name} was executed. Their role was {role}.').format(name=_name, role=_role))
            self.gameState.removePlayerByInfo(voteData.targetPlayer, RemoveReason.VOTE)
            self.trustRecorder.playerRemoved(voteData.targetPlayer, RemoveReason.VOTE)

    async def _processPlayerVote(self, voteData: VoteData, player: Player) :
        eveningPeriod: int = self.gameState.eveningSeconds
        rand = random.random()
        waitTime = 1.0 + rand * rand * eveningPeriod / 3.0

        await asyncio.sleep(waitTime)

        while self.gameState.currentPhase == Phase.EVENING :
            strategy: VoteStrategy = evaluator.evaluateVoteStrategy(self.gameState, self.trustRecorder, player)
            voteData.setVoteStrategy(player, strategy)
            self.trustRecorder.voteStrategyUpdated(player.info, strategy)

            await asyncio.sleep(random.uniform(0.1, 0.3) * eveningPeriod * 2.0 / 3.0)

    async def _processNight(self) :
        self.trustRecorder.updateTrustRecords()

        nightTargetData: NightTargetData = self.gameState.getCurrentNightTargetData()

        ### mafia action: kill
        # bot chooses the kill target
        if len(self.gameState.humanMafiaPlayers) == 0 and len(self.gameState.mafiaPlayers) > 0 :
            killTargetPlayer: Player = evaluator.evaluateKillTarget(self.gameState, self.trustRecorder)
            nightTargetData.killVoteData.setKillTarget(self.gameState.mafiaPlayers[0], killTargetPlayer)

        # local player chooses the kill target
        elif (
            self.gameState.localPlayer != None and
            self.gameState.localPlayer.isLive and
            self.gameState.localPlayer.info.role == Role.MAFIA
        ) :
            killTargetPlayer: Player = await self.gameState.getPlayerFromCuiAsync('Choose the target to assassinate: ')
            nightTargetData.killVoteData.setKillTarget(self.gameState.localPlayer, killTargetPlayer)

        ### police action: test
        police: Player = self.gameState.policePlayer

        if police.isLive :
            # local player chooses the test target
            if police.info.isLocalPlayer :
                nightTargetData.testTarget = await self.gameState.getPlayerFromCuiAsync('Choose the target to investigate: ')

            # bot chooses the test target
            elif not police.info.isHuman :
                nightTargetData.testTarget = evaluator.evaluateTestTarget(self.gameState, self.trustRecorder, police)

        ### doctor action: Heal
        doctor: Player = self.gameState.doctorPlayer

        if doctor.isLive :
            # local player chooses the heal target
            if doctor.info.isLocalPlayer :
                nightTargetData.healTarget = await self.gameState.getPlayerFromCuiAsync('Choose the target to heal: ')

            # bot chooses the heal target
            elif not doctor.info.isHuman :
                nightTargetData.healTarget = evaluator.evaluateHealTarget(self.gameState, self.trustRecorder, doctor)

        # await until time limit
        waitTime: float = self.gameState.timeLimit - time.monotonic()
        await asyncio.sleep(waitTime)

        ### execute kill
        doctor.addHealSuccess(None)
        killTargetPlayer: Player = nightTargetData.killVoteData.evaluate()

        if killTargetPlayer == None :
            self._addSystemChat(self._('The Mafia did not assassinate anyone.'))
        else :
            if killTargetPlayer == nightTargetData.healTarget :
                doctor.addHealSuccess(nightTargetData.healTarget)
                self.trustRecorder.healSucceeded(nightTargetData.healTarget.info)
                self._addSystemChat(self._('The Mafia attempted to assassinate someone but failed.'))
            else :
                self.gameState.removePlayerByInfo(killTargetPlayer.info, RemoveReason.KILL)
                self.trustRecorder.playerRemoved(killTargetPlayer.info, RemoveReason.KILL)
                _name = killTargetPlayer.info.name
                _role = self.gameState.translateRole[killTargetPlayer.info.role]
                self._addSystemChat(self._('{name} was assassinated by the Mafia. Their role was {role}.').format(name=_name, role=_role))

        ### execute test
        if nightTargetData.testTarget != None :
            police.addTestResult(nightTargetData.testTarget, nightTargetData.testTarget.info.role)
            _name = nightTargetData.testTarget.info.name

            visibleOnlyText = self._('This message visible only to you')
            mafiaNoticeText = ''

            if nightTargetData.testTarget.info.role == Role.MAFIA :
                mafiaNoticeText = self._('{name} is a Mafia.').format(name=_name)
            else :
                mafiaNoticeText = self._('{name} is not a Mafia.').format(name=_name)

            self._addSystemChat(
                content=f'({visibleOnlyText}) {mafiaNoticeText}',
                receiver=police.info,
            )
        else :
            police.addTestResult(None, None)

    def _addSystemChat(self, content, receiver: PlayerInfo = None) :
        self.gameState.appendSystemChat(content, receiver=receiver)
        self._printCUI(content)

    def _printCUI(self, text) :
        if self.gameState.gameInfo.isCUI :
            print(text)

    def checkGameEnd(self) -> GameEndInfo :
        survivorsListText = ', '.join(map(lambda p: str(p), self.gameState.players))
        self.gameState.logger.log(TAG.INFO, f'survivors list: {survivorsListText}')

        mafiaCount = len(self.gameState.mafiaPlayers)
        civilCount = len(self.gameState.players) - mafiaCount
        humanCount = len(list(filter(lambda p : p.info.isHuman, self.gameState.players)))

        if mafiaCount == 0 :
            self.gameState.logger.log(TAG.INFO, f'game end: it is a victory for the Citizens.')
            return GameEndInfo(
                reason=GameEndReason.CITIZEN_WIN,
            )
        elif civilCount <= mafiaCount :
            self.gameState.logger.log(TAG.INFO, f'game end: it is a victory for the Mafia.')
            return GameEndInfo(
                reason=GameEndReason.MAFIA_WIN,
            )
        elif humanCount == 0 and not self.gameState.continueOnlyBots :
            self.gameState.logger.log(TAG.INFO, f'game end: there are no human players.')
            return GameEndInfo(
                reason=GameEndReason.NO_HUMAN_PLAYER,
            )
        elif self.terminated :
            self.gameState.logger.log(TAG.INFO, f'game end: terminated.')
            return GameEndInfo(
                reason=GameEndReason.NO_HUMAN_PLAYER,
            )
        else :
            return None
