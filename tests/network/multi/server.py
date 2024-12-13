if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio
from multiprocessing import Process
import time
import traceback

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *

class MainProcess :
    async def main(self) :
        self.ipcServerTask = asyncio.create_task(self._startIpcServer())
        await self.ipcServerTask

    async def _startMainServer(self) :
        self.mainServer = TcpServer(port=10015)
        await self.mainServer.start(onConnected=self._onClientConnected)
        await self.mainServer.serve()

    async def _startIpcServer(self) :
        self.ipcServer = TcpServer(port=30000, useSSL=False)
        await self.ipcServer.start(onConnected=self._onIpcConnected)
        await self.ipcServer.serve()

    def _onClientConnected(self, tcpHandler: TcpHandler) :
        print(f'[Main] [Client] _onClientConnected')
        messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=lambda m: self._onClientAuth(messageHandler, m),
            onMessage=lambda m: self._onClientMessage(messageHandler, m),
            onDisconnected=lambda: self._onClientDisconnected(messageHandler),
        )

    def _onIpcConnected(self, tcpHandler: TcpHandler) :
        print(f'[Main] [IPC] _onIpcConnected')
        messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=None,
            onMessage=lambda m: self._onIpcMessage(messageHandler, m),
            onDisconnected=lambda: self._onIpcDisconnected(messageHandler),
        )

    def _onClientAuth(self, messageHandler: MessageHandler, message) :
        print(f'[Main] [Client] onAuth message=<{message}>')
        return True

    def _onClientMessage(self, messageHandler: MessageHandler, message) :
        print(f'[Main] [Client] onMessage message=<{message}>')
        message = game_pb2.GamePhase()
        message.round = self.gamePort
        messageHandler.send(message)

    def _onClientDisconnected(self, messageHandler: MessageHandler) :
        print('[Main] [Client] onDisconnected')

    def _onIpcMessage(self, messageHandler: MessageHandler, message) :
        print(f'[Main] [IPC] onMessage message=<{message}>')
        self.gamePort = message.round
        self.mainServerTask = asyncio.create_task(self._startMainServer())

    def _onIpcDisconnected(self, messageHandler: MessageHandler) :
        print('[Main] [IPC] onDisconnected')

class GameProcess :
    async def main(self, port: int) :
        self.port = port
        await self._startIpcClient()
        await self._startGameServer()

    async def _startIpcClient(self) :
        reader, writer = await asyncio.open_connection('127.0.0.1', 30000)
        tcpHandler = TcpHandler(reader, writer)
        self.ipcMessageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=None,
            onMessage=self._onIpcMessage,
            onDisconnected=self._onIpcDisconnected,
        )

    def _onIpcMessage(self, message) :
        print(f'[Game] [IPC] onMessage message=<{message}>')

    def _onIpcDisconnected(self) :
        print('[Game] [IPC] onDisconnected')

    async def _startGameServer(self) :
        while True :
            try :
                self.gameServer = TcpServer(port=self.port)
                await self.gameServer.start(onConnected=self._onClientConnected)
            except OSError as e :
                print(f'[Game] [Error] {e}')
                traceback.print_exc()
                self.port += 1
                await asyncio.sleep(1)
                continue
            break

        message = game_pb2.GamePhase()
        message.round = self.port
        self.ipcMessageHandler.send(message)

        await self.gameServer.serve()

    def _onClientConnected(self, tcpHandler: TcpHandler) :
        print(f'[Game] [Client] _onClientConnected')
        messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=lambda m: self._onClientAuth(messageHandler, m),
            onMessage=lambda m: self._onClientMessage(messageHandler, m),
            onDisconnected=lambda: self._onClientDisconnected(messageHandler),
        )

    def _onClientAuth(self, messageHandler: MessageHandler, message) :
        print(f'[Game] [Client] onAuth message=<{message}>')
        return True

    def _onClientMessage(self, messageHandler: MessageHandler, message) :
        print(f'[Game] [Client] onMessage message=<{message}>')
        messageHandler.send(message)

    def _onClientDisconnected(self, messageHandler: MessageHandler) :
        print('[Game] [Client] onDisconnected')

def startGameProcess() :
    time.sleep(2)
    gameProcess = GameProcess()
    asyncio.run(gameProcess.main(10016))

if __name__ == '__main__' :
    process = Process(target=startGameProcess)
    process.daemon = True
    process.start()

    mainProcess = MainProcess()
    asyncio.run(mainProcess.main())
