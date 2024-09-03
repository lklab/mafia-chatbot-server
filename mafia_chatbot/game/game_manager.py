from game.game_state import *
from game.llm import *

class GameManager :
    def __init__(self, gameInfo: GameInfo) :
        self.llm = LLM()
        self.gameState = GameState(gameInfo)
        print(self.gameState.players)

    def start(self) :
        pass
        # try :
        #     while True :
        #         message = input()
        #         response = self.llm.model.invoke(message)
        #         print(response.content)
        # except KeyboardInterrupt :
        #     print('terminated')
