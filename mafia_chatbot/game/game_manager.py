from enum import Enum

from game.game_state import *
import game.evaluator as evaluator
from game.llm import LLM

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
                strategy: Strategy = evaluator.evaluateVoteStrategy(self.gameState, players[index])
                player.setStrategy(strategy)
                discussion: str = self.llm.getDiscussion(self.gameState, player)
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
                target = player.strategy.mainTarget
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
                strategy: Strategy = evaluator.evaluateHealStrategy(self.gameState, doctor)
                healTarget = strategy.mainTarget
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
                strategy: Strategy = evaluator.evaluateKillStrategy(self.gameState, mafia)
                target: PlayerInfo = strategy.mainTarget
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
                strategy: Strategy = evaluator.evaluateTestStrategy(self.gameState, police)
                targetPlayer: Player = self.gameState.getPlayerByInfo(strategy.mainTarget)
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
