from enum import Enum

from mafia_chatbot.game.game_state import *
import mafia_chatbot.game.evaluator as evaluator
from mafia_chatbot.game.llm import LLM

class Phase(Enum) :
    DAY = 0
    EVENING = 1
    NIGHT = 2

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.gameState = GameState(gameInfo)
        self.llm = LLM()
        print(self.gameState.players)

    def start(self) :
        self.currentPhase = Phase.DAY
        self.discussionIndex = 0

        while True :
            if self.currentPhase == Phase.DAY :
                self.processDay()
                self.currentPhase = Phase.EVENING

            elif self.currentPhase == Phase.EVENING :
                self.processEvening()
                self.currentPhase = Phase.NIGHT

                if self.checkGameEnd() :
                    return

            elif self.currentPhase == Phase.NIGHT :
                self.processNight()
                self.currentPhase = Phase.DAY

                if self.checkGameEnd() :
                    return
                else :
                    self.gameState.addRound()

    def processDay(self) :
        print('\n아침이 되었습니다. 토론을 하세요')

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
                discussion: str = input('당신의 차례입니다: ')
                targetInfo: PlayerInfo = self.gameState.getPlayerInfoByName(discussion)
                strategy: Strategy = evaluator.getOneTargetStrategy(player.publicRole, targetInfo, '')
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

        print()

        players = self.gameState.players
        for player in players :
            if player.info.isAI :
                strategy: VoteStrategy = evaluator.evaluateVoteStrategy(self.gameState, player)
            else :
                targetName = input('투표할 대상을 정하세요: ')
                targetInfo: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)
                strategy: VoteStrategy = VoteStrategy(targetInfo)

            player.setVoteStrategy(self.gameState.round, strategy)

        voteData: VoteData = self.gameState.updateVoteHistory()
        print(f'투표 현황: {voteData.voteCount}')

        if voteData.isTie :
            print('동률로 인해 아무도 처형하지 않았습니다.')
        else :
            print(f'{voteData.targetPlayer.name}을 처형합니다. 그의 직업은 {voteData.targetPlayer.role.name}이었습니다.')
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
        # doctor action: Heal
        doctor: Player = self.gameState.doctorPlayer
        healTarget: PlayerInfo = None

        if doctor.isLive :
            print()
            if doctor.info.isAI :
                healTarget: PlayerInfo = evaluator.evaluateHealTarget(self.gameState, doctor).info
                print(f'의사는 {healTarget.name}을 치료합니다.')
            else :
                targetName = input('치료할 대상을 정하세요: ')
                healTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)

        # mafia action: kill
        print()

        killTarget: PlayerInfo = None
        if self.gameState.humanPlayer != None and self.gameState.humanPlayer.info.role == Role.MAFIA and self.gameState.humanPlayer.isLive :
            targetName = input('암살할 대상을 정하세요: ')
            killTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)
        else :
            killTarget: PlayerInfo = evaluator.evaluateKillTarget(self.gameState).info

        if killTarget == None :
            print('마피아의 실수로 암살에 실패했습니다.')
        else :
            if killTarget == healTarget :
                print(f'마피아는 {killTarget.name}을 암살하려 했지만 의사의 치료로 실패했습니다.')
            else :
                print(f'{killTarget.name}이 마피아에 의해 암살당했습니다.')
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
                targetName = input('조사할 대상을 정하세요: ')
                testTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)

        if testTarget != None :
            testTargetPlayer: Player = self.gameState.getPlayerByInfo(testTarget)
            police.addTestResult(testTargetPlayer, testTargetPlayer.info.role)
            print(f'경찰은 {testTargetPlayer.info.name}의 직업이 {testTargetPlayer.info.role.name}임을 확인했습니다.')

    def checkGameEnd(self) :
        mafiaCount = len(self.gameState.mafiaPlayers)
        civilCount = len(self.gameState.players) - mafiaCount

        if mafiaCount == 0 :
            print('\n시민의 승리입니다.')
            return True
        elif civilCount <= mafiaCount :
            print('\n마피아의 승리입니다.')
            return True
        else :
            return False

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
            self.updateTrustPoint(player)

        trustStr: list[str] = list(map(lambda p : f'{p.info.name}={p.trustPoint}({p.trustMainIssue})', self.gameState.players))
        print(', '.join(trustStr))

    def updateTrustPoint(self, player: Player) :
        # surely mafia
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
                if not p.isLive and p.info.role != estimation.role :
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

        # trusted police
        if player.publicRole == Role.POLICE and player.isTrustedPolice :
            player.setTrustData(TRUST_MAX)
            return

        # police's estimations
        if self.gameState.onePublicPolicePlayer != None :
            policePlayer = self.gameState.onePublicPolicePlayer
            if player.info in policePlayer.estimationsAsPolice :
                # the trusted police pointed me citizen
                if policePlayer.isTrustedPolice :
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
