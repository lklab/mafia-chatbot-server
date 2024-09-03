from game.game_manager import *
from game.game_state import *

if __name__ == "__main__" :
    gameInfo = GameInfo("Broccoli", 10, 3)
    manager = GameManager(gameInfo)
    manager.start()
