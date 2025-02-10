if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio
import uuid

from mafia_chatbot.game.game_state import GameState, languageToCodeDict, Phase
from mafia_chatbot.game.game_info import GameInfo
from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.chat_data import ChatData, ChatType

import mafia_chatbot.utils.name_bank as NameBank

async def main() :
    NameBank.initialize()

    for lang in ['korean'] : # languageToCodeDict.keys() :
        gameInfo: GameInfo = GameInfo(
            gameId=str(uuid.uuid4()),
            playerCount=10,
            mafiaCount=2,
            users=None,
            localPlayerName=None,
            language=lang,
        )

        gameManager: GameManager = GameManager(gameInfo)
        gameState: GameState = gameManager.gameState
        asyncio.create_task(gameManager.start())

        chatCount: int = 0

        while True :
            await asyncio.sleep(0.1)

            if len(gameState.chatList) > chatCount :
                for i in range(chatCount, len(gameState.chatList)) :
                    chat: ChatData = gameState.chatList[i]
                    if chat.type == ChatType.SYSTEM :
                        print(chat.content)
                    else :
                        print(chat.sender.name + ': ' + chat.content)
                chatCount = len(gameState.chatList)

            if gameState.currentPhase == Phase.EVENING :
                break

        gameManager.terminate()

asyncio.run(main())
