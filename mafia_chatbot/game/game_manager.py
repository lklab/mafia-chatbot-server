import asyncio
from datetime import datetime, timezone

from mafia_chatbot.game.game_state import *
from mafia_chatbot.game.game_result import *
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.client_message_processor import ClientMessageProcessor
from mafia_chatbot.game.game_end_info import GameEndInfo, GameEndReason

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.gameState = GameState(gameInfo)
        self.gameState.setOnHumanChatListener(self._onHumanChat)

        self.clientDict: dict[str, Player] = {}
        for player in self.gameState.players :
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

            if player.isLive :
                self._subscribeClient(player)
                return True
            else :
                self._sendGameEndToPlayer(player)
                return False
        else :
            return False

    def _subscribeClient(self, player: Player) :
        if player.client != None :
            ClientMessageProcessor(self.gameState, player)

    async def start(self) :
        await self._mainLogic()

    async def _mainLogic(self) :
        gameEndInfo: GameEndInfo = None

        while True :
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

        if gameEndInfo.reason != GameEndReason.NO_HUMAN_PLAYER :
            for player in self.clientDict.values() :
                if player.client != None :
                    message = game_pb2.GameEnd()

                    if gameEndInfo.reason == GameEndReason.CITIZEN_WIN :
                        message.reason = game_pb2.GameEndReason.GAME_END_CITIZEN_WIN
                    else :
                        message.reason = game_pb2.GameEndReason.GAME_END_MAFIA_WIN

                    player.client.sendMessage(message)

    async def _processDay(self) :
        self._addSystemChat('It is morning. Please engage in a discussion.')

        self.gameState.firstPointers.clear()

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

                self.updateAllTrustPoint()
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

        # record significant data
        if player.publicRole == Role.POLICE :
            self.gameState.addPublicPolice(player)

        for estimation in strategy.mafiaEstimations :
            p: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
            if p not in self.gameState.firstPointers :
                self.gameState.firstPointers[p] = player

    async def _processEvening(self) :
        self.updateAllTrustPoint()

        trustStr: list[str] = list(map(lambda p : f'{p.info.name}={p.trustPoint}({p.trustMainIssue})', self.gameState.players))
        self._printCUI('\n' + ', '.join(trustStr) + '\n')

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
            self.updateTrustRecordsForRemovedPlayer(voteData.targetPlayer, RemoveReason.VOTE)

            # update player.setTrustedPolice
            if voteData.targetPlayer.role == Role.MAFIA :
                for player in players :
                    if player.publicRole == Role.POLICE :
                        for estimation in player.estimationsAsPolice.values() :
                            if estimation.playerInfo == voteData.targetPlayer and estimation.role == Role.MAFIA :
                                player.setTrustedPolice()
                                break

    async def _processNight(self) :
        self.updateAllTrustPoint()

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
        if nightTargetData.killTarget == None :
            self._addSystemChat('The mafia did not assassinate anyone.')
        else :
            if nightTargetData.killTarget == nightTargetData.healTarget :
                self._addSystemChat(f'The Mafia attempted to assassinate {nightTargetData.killTarget.info.name}, but failed due to the doctor\'s healing.')
            else :
                self.gameState.removePlayerByInfo(nightTargetData.killTarget.info, RemoveReason.KILL)
                self.updateTrustRecordsForRemovedPlayer(nightTargetData.killTarget.info, RemoveReason.KILL)
                self._addSystemChat(f'{nightTargetData.killTarget.info.name} was assassinated by the Mafia.')

        ### execute test
        if nightTargetData.testTarget != None :
            police.addTestResult(nightTargetData.testTarget, nightTargetData.testTarget.info.role)
            self._addSystemChat(
                content=f'The police confirmed that {nightTargetData.testTarget.info.name}\'s role is {nightTargetData.testTarget.info.role.name}.',
                receiver=police.info,
            )

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
        elif humanCount == 0 :
            print('\nThere are no human players\n')

            players: list[Player] = list(self.clientDict.values())
            for player in players :
                if not player.isLive :
                    self._sendGameEndToPlayer(player)

            return GameEndInfo(
                reason=GameEndReason.NO_HUMAN_PLAYER,
            )
        else :
            players: list[Player] = list(self.clientDict.values())
            for player in players :
                if not player.isLive :
                    self._sendGameEndToPlayer(player)
            return None

    def _sendGameEndToPlayer(self, player: Player) :
        if player.isLive or player.client == None or player.client.id not in self.clientDict :
            return

        del self.clientDict[player.client.id]

        message = game_pb2.GameEnd()

        reason = self.gameState.getPlayerRemoveInfoByInfo(player.info).reason
        if reason == RemoveReason.VOTE :
            message.reason = game_pb2.GameEndReason.GAME_END_EXECUTED
        else :
            message.reason = game_pb2.GameEndReason.GAME_END_ASSASSINATED

        player.client.sendMessage(message)

    def updateTrustRecordsForRemovedPlayer(self, playerInfo: PlayerInfo, removeReason: RemoveReason) :
        removeInfo: PlayerRemoveInfo = self.gameState.getPlayerRemoveInfoByInfo(playerInfo)
        roundInfo: RoundInfo = removeInfo.roundInfo
        removedPlayer: Player = removeInfo.player

        playerCount = roundInfo.playerCount
        mafiaCount = roundInfo.mafiaCount
        civilCount = playerCount - mafiaCount

        if mafiaCount == 0 or civilCount <= mafiaCount :
            return

        if removedPlayer in self.gameState.firstPointers :
            player: Player = self.gameState.firstPointers[removedPlayer]

            # FIRST_POINT_CITIZEN
            if removedPlayer.info.role != Role.MAFIA :
                player.addTrustRecord(TrustRecord(
                    type=TrustRecordType.FIRST_POINT_CITIZEN,
                    point= -(removedPlayer.trustPoint + 100) / (playerCount - 2 * mafiaCount),
                ))

            # FIRST_POINT_MAFIA
            else :
                player.addTrustRecord(TrustRecord(
                    type=TrustRecordType.FIRST_POINT_MAFIA,
                    point= 100 / mafiaCount,
                ))

        # NOT_VOTE_MAFIA
        if removedPlayer.info.role == Role.MAFIA and removeReason == RemoveReason.VOTE :
            voteData: VoteData = self.gameState.getCurrentVoteData()
            notVoteTargetCount = len(voteData.notVoteTargetPlayers)

            for player in voteData.notVoteTargetPlayers :
                if player.isLive :
                    player.addTrustRecord(TrustRecord(
                        type=TrustRecordType.NOT_VOTE_MAFIA,
                        point= - 100 / notVoteTargetCount
                    ))

    def updateAllTrustPoint(self) :
        for player in self.gameState.players :
            self.updateSurelyMafia(player)
        for player in self.gameState.players :
            self.updateTrustPoint(player)

    def updateSurelyMafia(self, player: Player) :
        if player.publicRole == Role.MAFIA :
            player.setTrustData(
                TRUST_MIN,
                'He revealed that he is a mafia.',
            )
            return
        elif player.isContradictoryRole[0] :
            roles = player.isContradictoryRole[1]
            player.setTrustData(
                TRUST_MIN,
                f'He initially claimed his role was {roles[0].name.lower()}, but now he claims to be {roles[1].name.lower()}.',
            )
            return
        elif player.publicRole == Role.POLICE :
            if not self.gameState.isPoliceLive :
                player.setTrustData(
                    TRUST_MIN,
                    'Despite the police being already eliminated, he claims his role is a police.',
                )
                return

            mafiaEstimationCount = 0
            citizenEstimationCount = 0

            for estimation in player.estimationsAsPolice.values() :
                p = self.gameState.getPlayerByInfo(estimation.playerInfo)
                if p.publicRole == Role.POLICE :
                    player.setTrustData(
                        TRUST_MIN,
                        f'He claimed that {p.info.name} is a citizen, but {p.info.name} claims his role is a police.',
                    )
                    return
                if not p.isLive and ((p.info.role == Role.MAFIA) != (estimation.role == Role.MAFIA)) :
                    player.setTrustData(
                        TRUST_MIN,
                        'He incorrectly announced the role of an eliminated player.',
                    )
                    return

                if estimation.role == Role.MAFIA :
                    mafiaEstimationCount += 1
                else :
                    citizenEstimationCount += 1

            if self.gameState.gameInfo.mafiaCount < mafiaEstimationCount :
                player.setTrustData(
                    TRUST_MIN,
                    'There are too many mafia in his investigation results.',
                )
                return
            elif self.gameState.gameInfo.citizenCount < citizenEstimationCount :
                player.setTrustData(
                    TRUST_MIN,
                    'There are too many citizens in his investigation results.',
                )
                return

            if self.gameState.round < len(player.estimationsAsPolice) :
                player.setTrustData(
                    TRUST_MIN,
                    'There are contradictions in his investigation results. He has presented more investigation results than what is possible in the current round.',
                )
                return

    def updateTrustPoint(self, player: Player) :
        # trusted police
        if player.publicRole == Role.POLICE and player.isTrustedPolice :
            player.setTrustData(TRUST_MAX)
            return

        # one public police
        if player == self.gameState.onePublicPolicePlayer :
            player.setTrustData(TRUST_MAX)
            return

        # one police's estimations
        if self.gameState.onePublicPolicePlayer != None :
            policePlayer = self.gameState.onePublicPolicePlayer
            if policePlayer.trustPoint > TRUST_MIN and player.info in policePlayer.estimationsAsPolice :
                # the police pointed me citizen
                if policePlayer.estimationsAsPolice[player.info].role == Role.CITIZEN :
                    player.setTrustData(TRUST_MAX)
                    return

                # the police pointed me mafia
                if policePlayer.estimationsAsPolice[player.info].role == Role.MAFIA :
                    player.setTrustData(
                        TRUST_MIN,
                        'The police identified him as a mafia member.',
                    )
                    return

        # update trust data by record
        player.updateTrustDataByRecord()
