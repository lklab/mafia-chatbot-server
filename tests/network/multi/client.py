if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import ssl
import asyncio

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *

gamePort = None

def onMainMessage(message) :
    global gamePort
    print(f'onMainMessage message=<{message}>')
    if type(message) == game_pb2.GamePhase :
        gamePort = message.round

def onMainDisconnected() :
    print(f'onMainDisconnected')

def onGameMessage(message) :
    print(f'onGameMessage message=<{message}>')

def onGameDisconnected() :
    print(f'onGameDisconnected')

async def main() :
    global gamePort

    # main server part
    context = ssl._create_unverified_context()
    reader, writer = await asyncio.open_connection(
        '127.0.0.1', 10015, ssl=context
    )
    print('Connected to main server')

    tcpHandler = TcpHandler(reader, writer)
    messageHandler = MessageHandler(
        tcpHandler=tcpHandler,
        onAuth=None,
        onMessage=onMainMessage,
        onDisconnected=onMainDisconnected,
    )

    authMessage = auth_pb2.Auth()
    authMessage.rqid = '1'
    authMessage.clientId = '2'
    authMessage.name = '3'
    messageHandler.send(authMessage)
    print('send auth')

    messageHandler.send(authMessage)
    print('send data')
    while (gamePort == None) :
        await asyncio.sleep(0.1)

    await tcpHandler._close()
    print('Disconnected from main server')

    # game server part
    context = ssl._create_unverified_context()
    reader, writer = await asyncio.open_connection(
        '127.0.0.1', gamePort, ssl=context
    )
    print('Connected to game server')

    tcpHandler = TcpHandler(reader, writer)
    messageHandler = MessageHandler(
        tcpHandler=tcpHandler,
        onAuth=None,
        onMessage=onGameMessage,
        onDisconnected=onGameDisconnected,
    )

    authMessage = auth_pb2.Auth()
    authMessage.rqid = '1'
    authMessage.clientId = '2'
    authMessage.name = '3'
    messageHandler.send(authMessage)
    print('send auth')

    for i in range(1, 11) :
        message = game_pb2.GamePhase()
        message.round = i * i
        messageHandler.send(message)
        print('send data')
        await asyncio.sleep(1)

    await tcpHandler._close()
    print('Disconnected from game server')

if __name__ == '__main__' :
    asyncio.run(main())
