if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio

from mafia_chatbot.game.game_info import GameInfo, GameMode
from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.game_result import GameResult

playerCount = 10
mafiaCount = 2

def balanceTest(times: int) :
    citizenWinCount = 0
    policeRevealCount = 0
    citizenWinPolice = 0
    fakePoliceCount = 0

    for _ in range(100) :
        gameInfo = GameInfo(
            playerCount=playerCount,
            mafiaCount=mafiaCount,
            humanName=None,
            useLLM=False)

        manager = GameManager(gameInfo)
        gameResult: GameResult = manager.start()

        if gameResult.isCitizenWin :
            citizenWinCount += 1
        if gameResult.isRealPoliveRevealed :
            policeRevealCount += 1
            if gameResult.isCitizenWin :
                citizenWinPolice += 1
        if gameResult.isFakePoliveRevealed :
            fakePoliceCount += 1

    print(f'Citizen win rate: {citizenWinCount * 100 / times}, '
        'Number of police reveals: {policeRevealCount}, '
        'Win rate when police are revealed: {citizenWinPolice * 100 / policeRevealCount}, '
        'Number of false police reveals: {fakePoliceCount}'
    )

def oneGame() :
    gameInfo = GameInfo(
        playerCount=playerCount,
        mafiaCount=mafiaCount,
        clients=[],
        localPlayerName='Broccoli',
        language='english',
        gameMode=GameMode.CUI)

    manager = GameManager(gameInfo)
    asyncio.run(manager.start())

if __name__ == "__main__" :
    oneGame()
