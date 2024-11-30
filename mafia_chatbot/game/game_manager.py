import asyncio
from datetime import datetime, timezone

from mafia_chatbot.game.game_state import *
from mafia_chatbot.game.game_result import *
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.client_message_processor import ClientMessageProcessor
from mafia_chatbot.game.game_end_info import GameEndInfo, GameEndReason, gameEndReasonToProtoDict
from mafia_chatbot.game.trust_recorder import TrustRecorder

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.gameState = GameState(gameInfo)
        self.gameState.setOnHumanChatListener(self._onHumanChat)

        self.trustRecorder: TrustRecorder = TrustRecorder(self.gameState)

        self.clientDict: dict[str, Player] = {}
        for player in self.gameState.clientPlayers :
            if player.client != None :
                self.clientDict[player.client.id] = player
                self._subscribeClient(player)

        self.llm = LLM(self.gameState, gameInfo.language)

    def removeClient(self, client: ClientPlayer) :
        player = self.clientDict.get(client.id)
        if player != None :
            player.client = None

    def assignClient(self, client: ClientPlayer) :
        player = self.clientDict.get(client.id)
        if player != None :
            player.client = client
            self._subscribeClient(player)

    def _subscribeClient(self, player: Player) :
        if player.client != None :
            ClientMessageProcessor(self.gameState, self.trustRecorder, player)

    async def start(self) :
        await self._mainLogic()

    async def _mainLogic(self) :
        gameEndInfo: GameEndInfo = None

        while True :
            self.trustRecorder.startNewRound()

            self.gameState.setPhase(Phase.DAY)
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

        for player in self.gameState.clientPlayers :
            if player.client != None :
                message = game_pb2.GameEnd()
                message.reason = gameEndReasonToProtoDict[gameEndInfo.reason]
                player.client.sendMessage(message)

    async def _processDay(self) :
        self._addSystemChat('It is morning. Please engage in a discussion.')

        players = self.gameState.players
        playerCount = len(players)
        index = self.gameState.round % playerCount

        for _ in range(playerCount) :
            player: Player = players[index]
            index += 1
            index %= playerCount

            # for human player
            if player.info.isLocalPlayer :
                if self.gameState.gameInfo.useLLM :
                    discussion: str = input('It\'s your turn: ')
                    strategy: Strategy = self.llm.analyzeHumanMessage(player, discussion)
                    self._printCUI(f'human\'s strategy: {strategy}')
                else :
                    targetPlayer: Player = await self._getTargetFromCUI('It\'s your turn: ')
                    discussion: str = f'I think {targetPlayer.info.name} is a mafia'
                    strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, targetPlayer.info, '')

            # for bot player
            elif not player.info.isHuman :
                await asyncio.sleep(1)

                self.trustRecorder.updateTrustRecords()
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, players[index])

                if self.gameState.gameInfo.useLLM :
                    discussion: str = self.llm.getDiscussion(self.gameState, player, strategy)
                else :
                    discussion: str = str(strategy)

                self._printCUI(f'{player.info.name}: {discussion}')

            else :
                continue

            self._updateStrategy(player, strategy)
            self.gameState.appendDiscussionChat(player.info, discussion)

        # await until time limit
        waitTime: float = (self.gameState.timeLimit - datetime.now(timezone.utc)).total_seconds()
        await asyncio.sleep(waitTime)

    def _onHumanChat(self, chat: ChatData) :
        player: Player = self.gameState.getPlayerByInfo(chat.sender)

        if self.gameState.gameInfo.useLLM :
            strategy: Strategy = self.llm.analyzeHumanMessage(player, chat.content)
        else :
            target: Player = self.gameState.getPlayerByName(chat.content)
            if target == None :
                return
            strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, target.info, '')

        self._updateStrategy(player, strategy)

    def _updateStrategy(self, player: Player, strategy: Strategy) :
        # apply strategy and discussion
        player.setDiscussionStrategy(self.gameState.round, strategy)

        # record trust info
        self.trustRecorder.discussionStrategyUpdated(player.info, strategy)

    async def _processEvening(self) :
        self.trustRecorder.updateTrustRecords()

        cuiInputTask: asyncio.Task = None
        if self.gameState.localPlayer != None and self.gameState.localPlayer.isLive :
            cuiInputTask = asyncio.create_task(self._getTargetFromCUI('Choose the player to vote on: '))

        voteData: VoteData = self.gameState.getCurrentVoteData()
        players = self.gameState.players
        playerCount = len(players)
        index = 0

        def _setLocalPlayerStrategy(targetPlayer: Player) :
            strategy: VoteStrategy = VoteStrategy(targetPlayer.info)
            voteData.setVoteStrategy(self.gameState.localPlayer, strategy)
            self.trustRecorder.voteStrategyUpdated(self.gameState.localPlayer.info, strategy)

        while self.gameState.timeLimit > datetime.now(timezone.utc) :
            player: Player = players[index]
            index += 1
            index %= playerCount

            if cuiInputTask != None and cuiInputTask.done() :
                _setLocalPlayerStrategy(cuiInputTask.result())
                cuiInputTask = None

            if not player.info.isHuman :
                strategy: VoteStrategy = evaluator.evaluateVoteStrategy(self.gameState, player)
                voteData.setVoteStrategy(player, strategy)
                self.trustRecorder.voteStrategyUpdated(player.info, strategy)
                await asyncio.sleep(1)

        if cuiInputTask != None :
            targetPlayer: Player = await cuiInputTask
            _setLocalPlayerStrategy(targetPlayer)

        voteData.evaluate()
        self._printCUI(f'Voting status: {voteData.voteCount}')

        if voteData.isTie :
            self._addSystemChat('No one was executed due to a tie.')
        else :
            self._addSystemChat(f'{voteData.targetPlayer.name} is executed. Their role was {voteData.targetPlayer.role.name}.')
            self.gameState.removePlayerByInfo(voteData.targetPlayer, RemoveReason.VOTE)
            self.trustRecorder.playerRemoved(voteData.targetPlayer, RemoveReason.VOTE)

    async def _processNight(self) :
        self.trustRecorder.updateTrustRecords()

        nightTargetData: NightTargetData = self.gameState.getCurrentNightTargetData()

        ### mafia action: kill
        # bot chooses the kill target
        if len(self.gameState.humanMafiaPlayers) == 0 :
            nightTargetData.killTarget = evaluator.evaluateKillTarget(self.gameState)

        # local player chooses the kill target
        elif (
            self.gameState.localPlayer != None and
            self.gameState.localPlayer.isLive and
            self.gameState.localPlayer.info.role == Role.MAFIA
        ) :
            nightTargetData.killTarget = await self._getTargetFromCUI('Choose the target to assassinate: ')

        ### police action: test
        police: Player = self.gameState.policePlayer

        if police.isLive :
            # local player chooses the test target
            if police.info.isLocalPlayer :
                nightTargetData.testTarget = await self._getTargetFromCUI('Choose the target to investigate: ')

            # bot chooses the test target
            elif not police.info.isHuman :
                nightTargetData.testTarget = evaluator.evaluateTestTarget(self.gameState, police)

        ### doctor action: Heal
        doctor: Player = self.gameState.doctorPlayer

        if doctor.isLive :
            # local player chooses the heal target
            if doctor.info.isLocalPlayer :
                nightTargetData.healTarget = await self._getTargetFromCUI('Choose the target to heal: ')

            # bot chooses the heal target
            elif not doctor.info.isHuman :
                nightTargetData.healTarget = evaluator.evaluateHealTarget(self.gameState, doctor)

        # await until time limit
        waitTime: float = (self.gameState.timeLimit - datetime.now(timezone.utc)).total_seconds()
        await asyncio.sleep(waitTime)

        ### execute kill
        doctor.addHealSuccess(None)
        if nightTargetData.killTarget == None :
            self._addSystemChat('The mafia did not assassinate anyone.')
        else :
            if nightTargetData.killTarget == nightTargetData.healTarget :
                doctor.addHealSuccess(nightTargetData.healTarget)
                self.trustRecorder.healSucceeded(nightTargetData.healTarget.info)
                self._addSystemChat(f'The Mafia attempted to assassinate {nightTargetData.killTarget.info.name}, but failed due to the doctor\'s healing.')
            else :
                self.gameState.removePlayerByInfo(nightTargetData.killTarget.info, RemoveReason.KILL)
                self.trustRecorder.playerRemoved(nightTargetData.killTarget.info, RemoveReason.KILL)
                self._addSystemChat(f'{nightTargetData.killTarget.info.name} was assassinated by the Mafia.')

        ### execute test
        if nightTargetData.testTarget != None :
            police.addTestResult(nightTargetData.testTarget, nightTargetData.testTarget.info.role)
            self._addSystemChat(
                content=f'The police confirmed that {nightTargetData.testTarget.info.name}\'s role is {nightTargetData.testTarget.info.role.name}.',
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

    async def _getTargetFromCUI(self, text) -> Player :
        target: Player = None

        while target == None :
            name: str = await asyncio.get_running_loop().run_in_executor(None, input, text)
            target = self.gameState.getPlayerByName(name)

        return target

    def checkGameEnd(self) -> GameEndInfo :
        mafiaCount = len(self.gameState.mafiaPlayers)
        civilCount = len(self.gameState.players) - mafiaCount
        humanCount = len(list(filter(lambda p : p.info.isHuman, self.gameState.players)))

        if mafiaCount == 0 :
            print('\nIt is a victory for the Citizens.\n')
            return GameEndInfo(
                reason=GameEndReason.CITIZEN_WIN,
            )
        elif civilCount <= mafiaCount :
            print('\nIt is a victory for the Mafia.\n')
            return GameEndInfo(
                reason=GameEndReason.MAFIA_WIN,
            )
        elif humanCount == 0 and not self.gameState.continueOnlyBots :
            print('\nThere are no human players\n')
            return GameEndInfo(
                reason=GameEndReason.NO_HUMAN_PLAYER,
            )
        else :
            return None
