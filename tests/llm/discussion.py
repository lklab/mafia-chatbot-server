if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio
import uuid

from mafia_chatbot.game.game_info import GameInfo
from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.llm import LLM
from mafia_chatbot.game.game_logger import FakeGameLogger
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.strategy import Strategy

gameInfo = GameInfo(
    gameId=str(uuid.uuid4()),
    playerCount=10,
    mafiaCount=2,
    clients=None,
    localPlayerName='사바사',
    language='korean',
)
gameState = GameState(gameInfo, FakeGameLogger())
llm = LLM(gameState)

async def main() :
    global gameState, llm
    player: Player = gameState.getPlayerByName('사바사')

    names: list[str] = list(map(lambda p: p.info.name, filter(lambda p: not p.info.isHuman, gameState.players)))

    # result = await llm.checkContainsEstimation('태윤이 더 마피아같아')
    # print(result)
    # strategy = await llm.analyzeHumanMessage(player, '나는 태윤의 의견에 동의해서 진우가 마피아라고 생각해')
    strategy = await llm.analyzeHumanMessage(player, f'나는 {names[0]}의 의견에 반대해')
    print(strategy)
    # result = await llm._ainvokeChain(
    #     chain=llm.translateChain,
    #     input={
    #         'sentence': '유진이 마피아야'
    #     }
    # )
    # print(result)

asyncio.run(main())
