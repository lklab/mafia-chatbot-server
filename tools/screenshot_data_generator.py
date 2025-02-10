if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio
import uuid
import json

from mafia_chatbot.game.game_state import GameState, languageToCodeDict, Phase
from mafia_chatbot.game.game_info import GameInfo
from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.chat_data import ChatData, ChatType

import mafia_chatbot.utils.name_bank as NameBank

async def main() :
    NameBank.initialize()
    result = {}

    for lang in languageToCodeDict.keys() :
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

        data = {}
        result[lang] = data
        data['players'] = list(map(lambda p : p.info.name, gameState.players))

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

        chatListData = []
        data['chatList'] = chatListData

        for chat in gameState.chatList :
            if chat.type == ChatType.SYSTEM :
                chatListData.append({
                    'type': 'system',
                    'content': chat.content,
                })
            else :
                chatListData.append({
                    'type': 'discussion',
                    'sender': chat.sender.name,
                    'content': chat.content,
                })

        data['me'] = gameState.chatList[5].sender.name

    with open("screenshot_data.json", "w", encoding="utf-8") as f :
        json.dump(result, f, ensure_ascii=False, indent=4)

asyncio.run(main())
