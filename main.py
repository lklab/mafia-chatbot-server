from mafia_chatbot.game import *

if __name__ == "__main__" :
    gameInfo = game_info.GameInfo(
        playerCount=10,
        mafiaCount=3,
        humanName=None,
        useLLM=False)

    manager = game_manager.GameManager(gameInfo)
    manager.start()
