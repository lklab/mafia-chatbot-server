if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_client_handler import TcpClientHandler
from mafia_chatbot.network.message_client_handler import MessageClientHandler
from mafia_chatbot.network.data import *

client = None

def onMessage(message) :
    print(f'@@@ onMessage message=<{message}>')

    asyncio.create_task(sendMessage())

def onDisconnected() :
    print('@@@ onDisconnected')

async def sendMessage() :
    global client

    await asyncio.sleep(1)

    authResponse = auth_pb2.AuthResponse()
    authResponse.rqid = 777
    client.send(authResponse)

def onConnected(handler: TcpClientHandler) :
    global client
    client = MessageClientHandler(
        tcpHandler=handler,
        onMessage=onMessage,
        onDisconnected=onDisconnected,
    )

async def main() :
    server = TcpServer()
    await server.start(onConnected=onConnected)
    await server.serve()

asyncio.run(main())
