from game import *

if __name__ == "__main__" :
    gameInfo = game_info.GameInfo(
        humanName="Broccoli",
        playerCount=10,
        mafiaCount=3)
    manager = game_manager.GameManager(gameInfo)
    manager.start()
