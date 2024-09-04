from enum import Enum

from game.game_state import *
from game.llm import *

class Phase(Enum) :
    DAY = 0
    EVENING = 1
    NIGHT = 2

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.llm = LLM()
        self.gameState = GameState(gameInfo)

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

            elif self.currentPhase == Phase.NIGHT :
                self.processNight()
                self.currentPhase = Phase.DAY

    def processDay(self) :
        playerCount = self.gameState.gameInfo.playerCount
        for i in range(playerCount) :
            index = self.discussionIndex + i
            index %= playerCount
            self.evaluateStrategy(self.gameState.players[index])

        self.discussionIndex += 1
        self.discussionIndex %= playerCount

    def processEvening(self) :
        pass

    def processNight(self) :
        pass

    def evaluateStrategy(self, player: Player) :
        pass
