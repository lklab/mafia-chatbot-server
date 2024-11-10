import asyncio

from mafia_chatbot.game import *
from mafia_chatbot.game.game_result import *

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_client_handler import TcpClientHandler
from mafia_chatbot.network.message_client_handler import MessageClientHandler

class GameInstance :
    def __init__(self, handler: TcpClientHandler) :
        self.tcp = handler
        self.client = MessageClientHandler(
            tcpHandler=handler,
            onAuth=self._onAuth,
            onMessage=self._onMessage,
            onDisconnected=self._onDisconnected,
        )

    def _onAuth(self, message) :
        self._log(f'onAuth message=<{message}>')
        return True

    def _onMessage(self, message) :
        self._log(f'onMessage message=<{message}>')

    def _onDisconnected(self) :
        self._log(f'onDisconnected>')

    def _log(self, message) :
        print(f'[GameInstance] {self.tcp.addr}: {message}')

class MainProgram :
    def __init__(self) :
        pass

    async def run(self) :
        server = TcpServer()
        await server.start(onConnected=self._onConnected)
        await server.serve()

    def _onConnected(self, handler: TcpClientHandler) :
        GameInstance(handler)

if __name__ == "__main__" :
    program = MainProgram()
    asyncio.run(program.run())
