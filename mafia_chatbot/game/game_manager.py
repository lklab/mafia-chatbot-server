from enum import Enum

from game.game_state import *
import game.evaluator as evaluator

class Phase(Enum) :
    DAY = 0
    EVENING = 1
    NIGHT = 2

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.gameState = GameState(gameInfo)
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
                evaluator.evaluateVoteStrategy(self.gameState, players[index])
                print(player.getDiscussion())
            else :
                input('당신의 차례입니다: ')

        self.discussionIndex += 1
        self.discussionIndex %= playerCount

    def processEvening(self) :
        players = self.gameState.players
        voteDict: dict[PlayerInfo, int] = {}

        print()

        for player in players :
            if player.info.isAI :
                target = player.strategy.targets[0]
            else :
                targetName = input('투표할 대상을 정하세요: ')
                target = None
                for p in players :
                    if targetName == p.info.name :
                        target = p.info
                        break

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
        pass

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
