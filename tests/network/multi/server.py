if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio
from multiprocessing import Process
import traceback

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler

import mafia_chatbot.network.messages.message_info as MsgInfo

class MainProcess :
    async def main(self) :
        self.mainServerTask = asyncio.create_task(self._startMainServer())
        self.ipcServerTask = asyncio.create_task(self._startIpcServer())
        await self.mainServerTask

    async def _startMainServer(self) :
        self.mainServer = TcpServer(port=10015)
        await self.mainServer.start(onConnected=self._onClientConnected)
        await self.mainServer.serve()

    async def _startIpcServer(self) :
        self.ipcServer = TcpServer(port=30000, useSSL=False)
        await self.ipcServer.start(onConnected=self._onIpcConnected)
        await self.ipcServer.serve()

    def _onClientConnected(self, tcpHandler: TcpHandler) :
        messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=lambda m: self._onClientAuth(messageHandler, m),
            onMessage=lambda m: self._onClientMessage(messageHandler, m),
            onDisconnected=lambda: self._onClientDisconnected(messageHandler),
        )

    def _onIpcConnected(self, tcpHandler: TcpHandler) :
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

    def _onClientDisconnected(self, messageHandler: MessageHandler) :
        print('[Main] [Client] onDisconnected')

    def _onIpcMessage(self, messageHandler: MessageHandler, message) :
        print(f'[Main] [IPC] onMessage message=<{message}>')

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
            except OSError :
                self.port += 1
                continue
            break

        message = None # TODO 현재 포트에서 열었다고 알리기
        self.ipcMessageHandler.send(message)

        await self.gameServer.serve()

    def _onClientConnected(self, tcpHandler: TcpHandler) :
        pass

if __name__ == '__main__' :
    # m2sq = Queue()
    # s2mq = Queue()

    # process = Process(target=startGameProcess, args=(m2sq, s2mq))
    # process.daemon = True
    # process.start()

    mainProcess = MainProcess()
    asyncio.run(mainProcess.main())
