from mafia_chatbot.game import *
from mafia_chatbot.game.game_result import *

playerCount = 10
mafiaCount = 2

def balanceTest(times: int) :
    citizenWinCount = 0
    policeRevealCount = 0
    citizenWinPolice = 0
    fakePoliceCount = 0

    for _ in range(100) :
        gameInfo = game_info.GameInfo(
            playerCount=playerCount,
            mafiaCount=mafiaCount,
            humanName=None,
            useLLM=False)

        manager = game_manager.GameManager(gameInfo)
        gameResult: GameResult = manager.start()

        if gameResult.isCitizenWin :
            citizenWinCount += 1
        if gameResult.isRealPoliveRevealed :
            policeRevealCount += 1
            if gameResult.isCitizenWin :
                citizenWinPolice += 1
        if gameResult.isFakePoliveRevealed :
            fakePoliceCount += 1

    print(f'시민 승률: {citizenWinCount * 100 / times}, 경찰 공개 수: {policeRevealCount}, 경찰 공개 시 승률: {citizenWinPolice * 100 / policeRevealCount}, 거짓 경찰 공개 수: {fakePoliceCount}')

def oneGame() :
    gameInfo = game_info.GameInfo(
        playerCount=playerCount,
        mafiaCount=mafiaCount,
        humanName=None,
        useLLM=False)

    manager = game_manager.GameManager(gameInfo)
    manager.start()

if __name__ == "__main__" :
    balanceTest(100)
    # oneGame()
