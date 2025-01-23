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
import mafia_chatbot.utils.name_bank as NameBank

NameBank.initialize()

gameInfo = GameInfo(
    gameId=str(uuid.uuid4()),
    playerCount=10,
    mafiaCount=2,
    users=None,
    localPlayerName='시우',
    # localPlayerName='Sophia',
    language='korean',
)
gameState = GameState(gameInfo, FakeGameLogger())
llm = LLM(gameState)

async def main() :
    global gameState, llm
    player: Player = gameState.getPlayerByName('시우')
    # player: Player = gameState.getPlayerByName('Sophia')

    names: list[str] = list(map(lambda p: p.info.name, filter(lambda p: not p.info.isHuman, gameState.players)))

    # result = await llm.checkContainsEstimation('태윤이 더 마피아같아')
    # print(result)
    # strategy = await llm.analyzeHumanMessage(player, f'나는 {names[0]}의 의견에 동의해서 {names[1]}가 마피아라고 생각해')
    # strategy = await llm.analyzeHumanMessage(player, f'나는 {names[0]}이 시민라고 생각해. 왜냐면 내가 그를 암살로부터 구했어.')
    # strategy = await llm.analyzeHumanMessage(player, f'나는 마피아야.')
    # strategy = await llm.analyzeHumanMessage(player, f'나는 마피아가 아니야.')
    # strategy = await llm.analyzeHumanMessage(player, f'{names[0]}는 마피아가 아니야.')
    # strategy = await llm.analyzeHumanMessage(player, f'나도 {names[0]}이 의심스러워')
    # strategy = await llm.analyzeHumanMessage(player, f'{names[0]}에게 투표하자.')
    # strategy = await llm.analyzeHumanMessage(player, f'{names[0]} 너 마피아잖아')
    # strategy = await llm.analyzeHumanMessage(player, f'니가 마피아잖아.')
    # strategy = await llm.analyzeHumanMessage(player, f'마피아는 너야..')
    # strategy = await llm.analyzeHumanMessage(player, f'I am police and {names[0]} is a mafia')
    # strategy = await llm.analyzeHumanMessage(player, f'ㅁㄴㅁㄴㅇㅁㄴㅇㅈ')

    # print(f'{player.info.name}: {strategy}')

    # result = await llm._ainvokeChain(
    #     chain=llm.checkClaimsMafiaChain,
    #     input={
    #         'name': names[0],
    #         'sentence': f'{names[0]}은 마피아가 아니야.',
    #     }
    # )
    # print(result)

    # result = await llm._ainvokeChain(
    #     chain=llm.removeFirstPersonChain,
    #     input={
    #         'name' : 'Minjun',
    #         'sentence' : 'The mafia executed Seoyoon because they suspected he was a police informant.',
    #     }
    # )
    # print(result)

    print(await llm.isMessageQuestion('시우가 마피아라는 것에 대해 어떻게 생각해'))

asyncio.run(main())
