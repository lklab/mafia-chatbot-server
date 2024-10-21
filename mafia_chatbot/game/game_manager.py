from enum import Enum

from mafia_chatbot.game.game_state import *
from mafia_chatbot.game.game_result import *
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.llm import LLM

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.gameState = GameState(gameInfo)
        self.llm = LLM(self.gameState, gameInfo.language)
        print(self.gameState.players)

    def start(self) :
        self.discussionIndex = 0

        while True :
            if self.gameState.currentPhase == Phase.DAY :
                self.processDay()
                self.gameState.setPhase(Phase.EVENING)

            elif self.gameState.currentPhase == Phase.EVENING :
                self.processEvening()
                self.gameState.setPhase(Phase.NIGHT)

                gameResult: GameResult = self.checkGameEnd()
                if gameResult :
                    return gameResult

            elif self.gameState.currentPhase == Phase.NIGHT :
                self.processNight()
                self.gameState.setPhase(Phase.DAY)

                gameResult: GameResult = self.checkGameEnd()
                if gameResult :
                    return gameResult
                else :
                    self.gameState.addRound()

    def processDay(self) :
        print('\nIt is morning. Please engage in a discussion.')

        self.gameState.firstPointers.clear()

        players = self.gameState.players
        playerCount = len(players)
        for i in range(playerCount) :
            self.updateAllTrustPoint()

            index = self.discussionIndex + i
            index %= playerCount

            player = players[index]
            if player.info.isAI :
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, players[index])
                player.setDiscussionStrategy(self.gameState.round, strategy)

                if self.gameState.gameInfo.useLLM :
                    discussion: str = self.llm.getDiscussion(self.gameState, player)
                else :
                    discussion: str = str(strategy)

                discussion = f'{player.info.name}: {discussion}'
                self.gameState.appendDiscussionHistory(player.info, discussion)
                print(discussion)
            else :
                discussion: str = input('It\'s your turn: ')
                if self.gameState.gameInfo.useLLM :
                    strategy: Strategy = self.llm.analyzeHumanMessage(player, discussion)
                else :
                    targetInfo: PlayerInfo = self.gameState.getPlayerInfoByName(discussion)
                    strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, targetInfo, '')
                print(f'human\'s strategy: {strategy}')
                player.setDiscussionStrategy(self.gameState.round, strategy)
                discussion = f'{player.info.name}: {discussion}'

            self.gameState.appendDiscussionHistory(player.info, discussion)

            if player.publicRole == Role.POLICE :
                self.gameState.addPublicPolice(player)

            for estimation in strategy.mafiaEstimations :
                p: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
                if p not in self.gameState.firstPointers :
                    self.gameState.firstPointers[p] = player

        self.discussionIndex += 1
        self.discussionIndex %= playerCount

    def processEvening(self) :
        self.updateAllTrustPoint()

        trustStr: list[str] = list(map(lambda p : f'{p.info.name}={p.trustPoint}({p.trustMainIssue})', self.gameState.players))
        print('\n' + ', '.join(trustStr))

        print()

        players = self.gameState.players
        isHumanVoted: bool = False

        for _ in range(10) :
            for player in players :
                if player.info.isAI :
                    strategy: VoteStrategy = evaluator.evaluateVoteStrategy(self.gameState, player)
                else :
                    if not isHumanVoted :
                        targetName = input('Choose the player to vote on: ')
                        targetInfo: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)
                        if targetInfo != None :
                            strategy: VoteStrategy = VoteStrategy(targetInfo)
                            isHumanVoted = True
                        else :
                            continue
                    else :
                        continue

                player.setVoteStrategy(self.gameState.round, strategy)

        voteData: VoteData = self.gameState.updateVoteHistory()
        print(f'Voting status: {voteData.voteCount}')

        if voteData.isTie :
            print('No one was executed due to a tie.')
        else :
            print(f'{voteData.targetPlayer.name} is executed. Their role was {voteData.targetPlayer.role.name}.')
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

    def processNight(self) :
        self.updateAllTrustPoint()

        # doctor action: Heal
        doctor: Player = self.gameState.doctorPlayer
        healTarget: PlayerInfo = None

        if doctor.isLive :
            print()
            if doctor.info.isAI :
                healTarget: PlayerInfo = evaluator.evaluateHealTarget(self.gameState, doctor).info
                print(f'The doctor heals {healTarget.name}.')
            else :
                targetName = input('Choose the target to heal: ')
                healTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)

        # mafia action: kill
        print()

        killTarget: PlayerInfo = None
        if self.gameState.humanPlayer != None and self.gameState.humanPlayer.info.role == Role.MAFIA and self.gameState.humanPlayer.isLive :
            targetName = input('Choose the target to assassinate: ')
            killTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)
        else :
            killTarget: PlayerInfo = evaluator.evaluateKillTarget(self.gameState).info

        if killTarget == None :
            print('The assassination failed due to the Mafia\'s mistake.')
        else :
            if killTarget == healTarget :
                print(f'The Mafia attempted to assassinate {killTarget.name}, but failed due to the doctor\'s healing.')
            else :
                print(f'{killTarget.name} was assassinated by the Mafia.')
                self.gameState.removePlayerByInfo(killTarget, RemoveReason.KILL)
                self.updateTrustRecordsForRemovedPlayer(killTarget, RemoveReason.KILL)

        # police action: test
        police: Player = self.gameState.policePlayer
        testTarget: PlayerInfo = None

        if police.isLive :
            print()
            if police.info.isAI :
                testTargetPlayer: Player = evaluator.evaluateTestTarget(self.gameState, police)
                if testTargetPlayer != None :
                    testTarget: PlayerInfo = testTargetPlayer.info
            else :
                targetName = input('Choose the target to investigate: ')
                testTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)

        if testTarget != None :
            testTargetPlayer: Player = self.gameState.getPlayerByInfo(testTarget)
            police.addTestResult(testTargetPlayer, testTargetPlayer.info.role)
            print(f'The police confirmed that {testTargetPlayer.info.name}\'s role is {testTargetPlayer.info.role.name}.')

    def checkGameEnd(self) :
        mafiaCount = len(self.gameState.mafiaPlayers)
        civilCount = len(self.gameState.players) - mafiaCount

        if mafiaCount == 0 :
            print('\nIt is a victory for the Citizens.\n')
            return GameResult(
                isCitizenWin=True,
                isRealPoliveRevealed=self.gameState.isRealPoliveRevealed,
                isFakePoliveRevealed=self.gameState.isFakePoliveRevealed,
            )
        elif civilCount <= mafiaCount :
            print('\nIt is a victory for the Mafia.\n')
            return GameResult(
                isCitizenWin=False,
                isRealPoliveRevealed=self.gameState.isRealPoliveRevealed,
                isFakePoliveRevealed=self.gameState.isFakePoliveRevealed,
            )
        else :
            return None

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
