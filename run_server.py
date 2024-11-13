import asyncio
from typing import Callable, Any

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.client_player import ClientPlayer

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_client_handler import TcpClientHandler
from mafia_chatbot.network.message_client_handler import MessageClientHandler

class ClientHandler :
    pass

class ClientHandler :
    def __init__(
            self,
            tcp: TcpClientHandler,
            onAuth: Callable[[ClientHandler, Any], bool],
            onMessage: Callable[[ClientHandler, Any], None],
            onDisconnected: Callable[[ClientHandler], None],
        ) :
        self.tcp = tcp

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.clientId: str = None

        self.messageHandler = MessageClientHandler(
            tcpHandler=tcp,
            onAuth=self._onAuth,
            onMessage=self._onMessage,
            onDisconnected=self._onDisconnected,
        )

        self.player = ClientPlayer(
            id=self.clientId,
            name='test name',
            client=self.messageHandler,
        )

    def getPlayer(self) :
        return self.player

    def _onAuth(self, message) :
        self._log(f'onAuth message=<{message}>')
        self.clientId = message.clientId
        return self.onAuth(self, message)

    def _onMessage(self, message) :
        self._log(f'onMessage message=<{message}>')
        self.onMessage(self, message)

    def _onDisconnected(self) :
        self._log(f'onDisconnected>')
        self.onDisconnected(self)

    def _log(self, message) :
        print(f'[ClientHandler] {self.tcp.addr}: {message}')

class MainProgram :
    def __init__(self) :
        self.clientDict: dict[str, ClientHandler] = {}
        self.gameDict: dict[str, GameManager] = {}

    async def run(self) :
        server = TcpServer()
        await server.start(onConnected=self._onClientConnected)
        await server.serve()

    def _onClientConnected(self, handler: TcpClientHandler) :
        ClientHandler(
            tcp=handler,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
        )

    def _onClientAuth(self, client: ClientHandler, message) :
        self.clientDict[client.clientId] = client

        if client.clientId in self.gameDict :
            self.gameDict[client.clientId].assignClient(client.getPlayer())

        return True

    def _onClientMessage(self, client: ClientHandler, message) :
        client.getPlayer().forwardMessage(message)

    def _onClientDisconnected(self, client: ClientHandler) :
        if client.clientId in self.gameDict :
            self.gameDict[client.clientId].removeClient(client.getPlayer())

        if client.clientId in self.clientDict :
            del self.clientDict[client.clientId]

if __name__ == "__main__" :
    program = MainProgram()
    asyncio.run(program.run())
