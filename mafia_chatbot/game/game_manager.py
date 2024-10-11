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

        players = self.gameState.players
        playerCount = len(players)
        for i in range(playerCount) :
            self.updateAllTrustPoint()

            index = self.discussionIndex + i
            index %= playerCount

            player = players[index]
            if player.info.isAI :
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, players[index])
                player.setDiscussionStrategy(strategy)

                if self.gameState.gameInfo.useLLM :
                    discussion: str = self.llm.getDiscussion(self.gameState, player)
                else :
                    discussion: str = str(strategy)

                self.gameState.appendDiscussionHistory(player.info, discussion)
                print(f'{player.info.name}: {discussion}')

                # TODO move it out of the if statement
                for estimation in strategy.mafiaEstimations :
                    p: Player = self.gameState.getPlayerByInfo(estimation.playerInfo)
                    if p not in self.gameState.firstPointers :
                        self.gameState.firstPointers[p] = player
            else :
                discussion: str = input('당신의 차례입니다: ')
                self.gameState.appendDiscussionHistory(player.info, discussion)

            if player.publicRole == Role.POLICE :
                self.gameState.addPublicPolice(player)

        self.discussionIndex += 1
        self.discussionIndex %= playerCount

    def processEvening(self) :
        self.updateAllTrustPoint()

        print()

        players = self.gameState.players
        for player in players :
            if player.info.isAI :
                strategy: VoteStrategy = evaluator.evaluateVoteTarget(self.gameState, player)
                player.setVoteStrategy(self.gameState.round, strategy)
            else :
                # TODO
                pass

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
            if doctor.info.isAI :
                healTarget = evaluator.evaluateHealTarget(self.gameState, doctor)
                print()
                print(f'의사는 {healTarget.name}을 치료합니다.')
            else :
                print()
                targetName = input('치료할 대상을 정하세요: ')
                healTarget: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)

        # mafia action: kill
        print()
        killVoteDict: dict[PlayerInfo, int] = {}

        for mafia in self.gameState.mafiaPlayers :
            if mafia.info.isAI :
                target: PlayerInfo = evaluator.evaluateKillTarget(self.gameState, mafia)
            else :
                targetName = input('암살할 대상을 정하세요: ')
                target: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)

            if target is not None :
                if target not in killVoteDict :
                    killVoteDict[target] = 0
                killVoteDict[target] += 1

        print(f'암살 투표 현황: {killVoteDict}')

        maxKillVote = 0
        maxKillTargets: list[PlayerInfo] = []

        for playerInfo, vote in killVoteDict.items() :
            if maxKillVote == vote :
                maxKillTargets.append(playerInfo)
            elif maxKillVote < vote :
                maxKillVote = vote
                maxKillTargets.clear()
                maxKillTargets.append(playerInfo)

        if len(maxKillTargets) == 0 :
            print('마피아의 실수로 암살에 실패했습니다.')
        else :
            killTarget: PlayerInfo = random.choice(maxKillTargets)
            if killTarget == healTarget :
                print(f'마피아는 {killTarget.name}을 암살하려 했지만 의사의 치료로 실패했습니다.')
            else :
                print(f'{killTarget.name}이 마피아에 의해 암살당했습니다.')
                self.gameState.removePlayerByInfo(killTarget, RemoveReason.KILL)
                self.updateTrustRecordsForRemovedPlayer(killTarget, RemoveReason.KILL)

        # police action: test
        police: Player = self.gameState.policePlayer
        if police.isLive :
            if police.info.isAI :
                target: PlayerInfo = evaluator.evaluateTestTarget(self.gameState, police)
                targetPlayer: Player = self.gameState.getPlayerByInfo(target)
                police.addTestResult(targetPlayer, targetPlayer.info.role)
                print()
                print(f'경찰은 {targetPlayer.info.name}의 직업이 {targetPlayer.info.role}임을 확인했습니다.')
            else :
                print()
                targetName = input('조사할 대상을 정하세요: ')
                target: PlayerInfo = self.gameState.getPlayerInfoByName(targetName)
                if target != None :
                    print(f'{target.name}의 직업은 {target.role} 입니다.')

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

    def updateAllTrustPoint(self) :
        for player in self.gameState.players :
            self.updateTrustPoint(player)

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
