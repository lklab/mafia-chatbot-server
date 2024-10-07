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

    def processDay(self) :
        print('\n아침이 되었습니다. 토론을 하세요')

        players = self.gameState.players
        playerCount = len(players)
        for i in range(playerCount) :
            index = self.discussionIndex + i
            index %= playerCount

            player = players[index]
            if player.info.isAI :
                strategy: Strategy = evaluator.evaluateDiscussionStrategy(self.gameState, players[index])
                player.setStrategy(strategy)

                if self.gameState.gameInfo.useLLM :
                    discussion: str = self.llm.getDiscussion(self.gameState, player)
                else :
                    discussion: str = strategy.getDescription()

                self.gameState.appendDiscussionHistory(player.info, discussion)
                print(f'{player.info.name}: {discussion}')
            else :
                discussion: str = input('당신의 차례입니다: ')
                self.gameState.appendDiscussionHistory(player.info, discussion)

        self.discussionIndex += 1
        self.discussionIndex %= playerCount

    def processEvening(self) :
        print()

        players = self.gameState.players
        voteDict: dict[PlayerInfo, int] = {}

        for player in players :
            if player.info.isAI :
                target = evaluator.evaluateVoteTarget(self.gameState, player)
            else :
                targetName = input('투표할 대상을 정하세요: ')
                target = self.gameState.getPlayerInfoByName(targetName)

            if target is not None :
                if target not in voteDict :
                    voteDict[target] = 0
                voteDict[target] += 1

        print(f'투표 현황: {voteDict}')

        isTie = False
        maxVote = 0
        maxPlayer: PlayerInfo = None

        for playerInfo, vote in voteDict.items() :
            if maxVote == vote :
                isTie = True
            elif maxVote < vote :
                isTie = False
                maxVote = vote
                maxPlayer = playerInfo

        if isTie :
            print('동률로 인해 아무도 처형하지 않았습니다.')
        else :
            print(f'{maxPlayer.name}을 처형합니다. 그의 직업은 {maxPlayer.role.name}이었습니다.')
            self.gameState.removePlayerByInfo(maxPlayer)

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
                self.gameState.removePlayerByInfo(killTarget)

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
        civilCount = 0
        mafiaCount = 0
        for player in self.gameState.players :
            if player.info.role == Role.MAFIA :
                mafiaCount += 1
            else :
                civilCount += 1

        if mafiaCount == 0 :
            print('\n시민의 승리입니다.')
            return True
        elif civilCount <= mafiaCount :
            print('\n마피아의 승리입니다.')
            return True
        else :
            return False

    def updateTrustPoint(self, player: Player) :
        # surely mafia
        if player.publicRole == Role.MAFIA :
            player.setTrustData(TRUST_MIN, 'He revealed that he is a mafia.')
            return
        elif player.isContradictoryRole[0] :
            roles = player.isContradictoryRole[1]
            player.setTrustData(TRUST_MIN, f'He initially claimed his role was {roles[0].name.lower()}, but now he claims to be {roles[1].name.lower()}.')
            return
        elif player.publicRole == Role.POLICE :
            if not self.gameState.isPoliceLive :
                player.setTrustData(TRUST_MIN, 'Despite the police being already eliminated, he claims his role is a police.')
                return

            mafiaEstimationCount = 0
            citizenEstimationCount = 0

            for estimation in player.estimationsAsPolice.values() :
                p = self.gameState.getPlayerByInfo(estimation.playerInfo)
                if p.publicRole == Role.POLICE :
                    player.setTrustData(TRUST_MIN, f'He claimed that {p.info.name} is a citizen, but {p.info.name} claims his role is a police.')
                    return
                if not p.isLive and p.info.role != estimation.role :
                    player.setTrustData(TRUST_MIN, 'He incorrectly announced the role of an eliminated player.')
                    return

                if estimation.role == Role.MAFIA :
                    mafiaEstimationCount += 1
                else :
                    citizenEstimationCount += 1

            if self.gameState.gameInfo.mafiaCount < mafiaEstimationCount :
                player.setTrustData(TRUST_MIN, 'There are too many mafia in his investigation results.')
                return
            elif self.gameState.gameInfo.citizenCount < citizenEstimationCount :
                player.setTrustData(TRUST_MIN, 'There are too many citizens in his investigation results.')
                return

            if self.gameState.round < len(player.estimationsAsPolice) :
                player.setTrustData(TRUST_MIN, 'There are contradictions in his investigation results. He has presented more investigation results than what is possible in the current round.')
                return

        # calculate trust point
        total = 0
        maxDecreasePoint = 0
        mainIssue = ''

        # pointed citizens
        point = 0
        for playerInfo in player.firstMafiaAssumptions :
            p = self.gameState.getPlayerByInfo(playerInfo)
            if not p.isLive and p.info.role != Role.MAFIA :
                point -= max(p.trustPoint, 0) + 10

        total += point
        if point < maxDecreasePoint :
            maxDecreasePoint = point
            mainIssue = 'He pointed out the citizen first.'

        # pointed mafias
        for playerInfo in player.voteHistory :
            p = self.gameState.getPlayerByInfo(playerInfo)
            if not p.isLive and p.info.role == Role.MAFIA :
                point += 10

        # not pointed surely mafia


        # update trust data
        player.setTrustData(total, mainIssue)
