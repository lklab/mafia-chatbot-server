import asyncio
from typing import Callable, Any

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.game_info import GameInfo, GameMode

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_client_handler import TcpClientHandler
from mafia_chatbot.network.message_client_handler import MessageClientHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

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

        self.messageHandler = MessageClientHandler(
            tcpHandler=tcp,
            onAuth=self._onAuth,
            onMessage=self._onMessage,
            onDisconnected=self._onDisconnected,
        )

        self.player = None
        self.clientId = None

    def getPlayer(self) -> ClientPlayer :
        return self.player

    def _onAuth(self, message) :
        self._log(f'onAuth message=<{message}>')

        self.player = ClientPlayer(
            id=message.clientId,
            name=message.name,
            client=self.messageHandler,
        )
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

class Game :
    def __init__(self, gameInfoMessage: game_pb2.GameInfo, clients: list[ClientHandler]) :
        self.gameInfoMessage = gameInfoMessage
        self.clients = clients

        self.gameInfo = GameInfo(
            playerCount=gameInfoMessage.playerCount,
            mafiaCount=gameInfoMessage.mafiaCount,
            clients=list(map(lambda c : c.getPlayer(), clients)),
            localPlayerName=None,
            language=gameInfoMessage.language,
            gameMode=GameMode.CLIENT
        )

    def checkValid(self) -> bool :
        return self.gameInfo.checkValid()

    def setupManager(self) :
        if self.checkValid() :
            self.manager = GameManager(self.gameInfo)

class MainProgram :
    def __init__(self) :
        self.gameDict: dict[str, Game] = {}

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
        # TODO check auth message
        return True

    def switchMessageRequestMyGameInfo(self, client: ClientHandler, message) :
        if client.clientId in self.gameDict :
            response = game_pb2.MyGameInfo()
            response.rqid = message.rqid
            response.isGameExists = True
            response.info.CopyFrom(self.gameDict[client.clientId].gameInfoMessage)
            client.messageHandler.send(response)

        else :
            response = game_pb2.MyGameInfo()
            response.rqid = message.rqid
            response.isGameExists = False
            client.messageHandler.send(response)

    def _switchMessageGameStart(self, client: ClientHandler, message) :
        if client.clientId in self.gameDict :
            errorResponse = self._makeErrorResponse(message, 0, 'The game is already running.')
            client.messageHandler.send(errorResponse)
            return

        game: Game = Game(message.info, [client])

        if not game.checkValid() :
            errorResponse = self._makeErrorResponse(message, 0, 'GameInfo is invalid.')
            client.messageHandler.send(errorResponse)
            return

        game.setupManager()

        response = game_pb2.GameStartResponse()
        response.rqid = message.rqid
        client.messageHandler.send(response)

        asyncio.create_task(self._runGame(game))

    def switchMessageJoinMyGame(self, client: ClientHandler, message) :
        if client.clientId in self.gameDict :
            self.gameDict[client.clientId].manager.assignClient(client.getPlayer())

            response = game_pb2.JoinMyGameResponse()
            response.rqid = message.rqid
            client.messageHandler.send(response)

        else :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            client.messageHandler.send(errorResponse)
            return

    _switchMessage = {
        game_pb2.RequestMyGameInfo : switchMessageRequestMyGameInfo,
        game_pb2.GameStart : _switchMessageGameStart,
        game_pb2.JoinMyGame : switchMessageJoinMyGame,
    }

    def _onClientMessage(self, client: ClientHandler, message) :
        if type(message) in MainProgram._switchMessage :
            MainProgram._switchMessage[type(message)](self, client, message)
        else :
            client.getPlayer().forwardMessage(message)

    def _onClientDisconnected(self, client: ClientHandler) :
        if client.clientId in self.gameDict :
            self.gameDict[client.clientId].manager.removeClient(client.getPlayer())

    def _makeErrorResponse(self, message, code: int, detail: str) :
        print(f'@@@ error response: {detail}')
        errorResponse = error_pb2.RequestError()
        errorResponse.rqid = message.rqid
        errorResponse.rqtype = messageTypeDict[type(message)]
        errorResponse.code = code
        errorResponse.detail = detail
        return errorResponse

    async def _runGame(self, game: Game) :
        for client in game.clients :
            self.gameDict[client.clientId] = game

        await game.manager.start()

        for client in game.clients :
            del self.gameDict[client.clientId]

if __name__ == "__main__" :
    program = MainProgram()
    asyncio.run(program.run())
