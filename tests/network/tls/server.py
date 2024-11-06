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

def onMessage(type: int, data: bytes) :
    message = data.decode()
    print(f'@@@ onMessage {type}, {message}')

def onDisconnected() :
    print('@@@ onDisconnected')

def onConnected(handler: TcpClientHandler) :
    asyncio.create_task(handler.listen(
        onMessage=onMessage,
        onDisconnected=onDisconnected,
    ))

    asyncio.create_task(handler.sendStr(77, 'Hello, this is test haha.'.encode()))

async def main() :
    server = TcpServer()
    await server.start(onConnected=onConnected)
    await server.serve()

asyncio.run(main())
