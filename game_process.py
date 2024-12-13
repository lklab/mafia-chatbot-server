import asyncio
from multiprocessing import Process
import time
import datetime
import uuid
import os
import json
from typing import Callable

from client_handler import ClientHandler

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.game_info import GameInfo, DebugInfo

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

MAIN_PROCESS_PORT = 30000

class GameInstance :
    pass

class GameInstance :
    def __init__(self, id: str, clientIds: list[str]) :
        self.id = id
        self.clientIds = clientIds

        self.gameInfoMessage: game_pb2.GameInfo = None
        self.gameInfo: GameInfo = None

        self.gameManager: GameManager = None

    def setGameInfoMessage(self, message: game_pb2.GameInfo) :
        self.gameInfoMessage = message

    def prepareGame(self, clients: list[ClientHandler]) -> bool :
        if self.gameManager != None :
            return False
        self.gameInfo = self._setupGameInfo(clients)
        return self.gameInfo.checkValid()

    def startGame(self, onGameEnded: Callable[[GameInstance], None]) :
        async def _startGame() :
            await self.gameManager.start()
            onGameEnded(self)

        if self.gameManager != None or self.gameInfo == None :
            return

        self.gameManager = GameManager(self.id, self.gameInfo)
        asyncio.create_task(_startGame())

    def isRunning(self) :
        return self.gameManager != None

    def connectClient(self, client: ClientHandler) :
        if self.gameManager != None :
            self.gameManager.connectClient(client.getPlayer())

    def disconnectClient(self, client: ClientHandler) :
        if self.gameManager != None :
            self.gameManager.disconnectClient(client.clientId)

    def removeClient(self, client: ClientHandler) :
        try:
            self.clientIds.remove(client)
        except ValueError:
            pass

        if self.gameManager != None :
            self.gameManager.removeClient(client.clientId)

    def _setupGameInfo(self, clients: list[ClientHandler]) :
        self.gameInfo = GameInfo(
            playerCount=self.gameInfoMessage.playerCount,
            mafiaCount=self.gameInfoMessage.mafiaCount,
            clients=list(map(lambda c : c.getPlayer(), clients)),
            localPlayerName=None,
            language=self.gameInfoMessage.language,
            debugInfo=DebugInfo(self.gameInfoMessage.debugInfo) if self.gameInfoMessage.debugInfo.isDebug else None,
        )

class GameProcess :
    def __init__(self, port: int) :
        self.port: int = port

        self.clients: dict[str, ClientHandler] = {}
        self.gameByClientId: dict[str, GameInstance] = {}

    async def run(self) :
        # start game server
        while True :
            try :
                gameServer = TcpServer(port=self.port)
                await gameServer.start(onConnected=self._onClientConnected)
            except OSError as e :
                self.port += 1
                await asyncio.sleep(0.3)
                continue
            break

        # connect to main process
        reader, writer = await asyncio.open_connection('127.0.0.1', MAIN_PROCESS_PORT)
        mainProcessTcpHandler = TcpHandler(reader, writer)
        self.mainProcessMessageHandler = MessageHandler(
            tcpHandler=mainProcessTcpHandler,
            onAuth=None,
            onMessage=self._onMainProcessMessage,
            onDisconnected=self._onMainProcessDisconnected,
        )

        # send GameServerStarted message to main process
        message = game_pb2.GameServerStarted()
        message.port = self.port
        self.mainProcessMessageHandler.send(message)

        # serve game server
        await gameServer.serve()

    ### Handle main process ###
    def _onMainProcessMessage(self, message) :
        print(f'[GameProcess] _onMainProcessMessage message=<{message}>')
        if type(message) in GameProcess._switchMainProcessMessage :
            GameProcess._switchMainProcessMessage[type(message)](self, message)

    def _onMainProcessDisconnected(self) :
        print('[GameProcess] _onMainProcessDisconnected') # ERROR!!

    def _switchMainProcessMessageStartNewGame(self, message) :
        # prepare game
        gameId: str = message.gameId
        clientIds: list[str] = message.clients

        game: GameInstance = GameInstance(gameId, clientIds)
        for cliendId in clientIds :
            self.gameByClientId[cliendId] = game

        # send response to main process
        response = ipc_pb2.StartNewGameResponse()
        response.rqid = message.rqid
        self.mainProcessMessageHandler.send(response)

    _switchMainProcessMessage = {
        ipc_pb2.StartNewGame : _switchMainProcessMessageStartNewGame,
    }

    ### Handle client ###
    def _onClientConnected(self, tcpHandler: TcpHandler) :
        print(f'[GameProcess] _onClientConnected')
        ClientHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
        )

    def _onClientAuth(self, client: ClientHandler, message) :
        print(f'[GameProcess] _onClientAuth name={message.name}, message=<{message}>')
        clientId: str = message.clientId

        if clientId in self.gameByClientId :
            self.clients[clientId] = client

            game: GameInstance = self.gameByClientId[clientId]
            game.connectClient(client)

            return True
        else :
            return False

    def _onClientMessage(self, client: ClientHandler, message) :
        print(f'[GameProcess] _onClientMessage name={client.clientName}, message=<{message}>')
        if type(message) in GameProcess._switchClientMessage :
            GameProcess._switchClientMessage[type(message)](self, client, message)
        else :
            client.getPlayer().forwardMessage(message)

    def _onClientDisconnected(self, client: ClientHandler) :
        print(f'[GameProcess] _onClientDisconnected name={client.clientName}')
        if client.clientId in self.clients :
            del self.clients[client.clientId]
        if client.clientId in self.gameByClientId :
            game: GameInstance = self.gameByClientId[client.clientId]
            game.disconnectClient(client)

    def _switchClientMessageRequestTimeSync(self, client: ClientHandler, message) :
        response = time_pb2.TimeSync()
        response.rqid = message.rqid
        response.time = time.monotonic()
        client.messageHandler.send(response)

    def _switchClientMessageRequestGameInfo(self, client: ClientHandler, message) :
        if client.clientId not in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            client.messageHandler.send(errorResponse)
            return

        game: GameInstance = self.gameByClientId[client.clientId]
        if game.gameInfoMessage == None :
            errorResponse = self._makeErrorResponse(message, 0, 'Game info not set yet.')
            client.messageHandler.send(errorResponse)
            return

        response = game_pb2.MyGameInfo()
        response.CopyFrom(game.gameInfoMessage)
        client.messageHandler.send(response)

    def _switchClientMessageGameStart(self, client: ClientHandler, message) :
        if client.clientId not in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            client.messageHandler.send(errorResponse)
            return

        game: GameInstance = self.gameByClientId[client.clientId]
        if game.isRunning() :
            errorResponse = self._makeErrorResponse(message, 0, 'The game is already running.')
            client.messageHandler.send(errorResponse)
            return

        game.setGameInfoMessage(message.info)

        clients: list[ClientHandler] = []
        for clientId in game.clientIds :
            if clientId in self.clients :
                clients.append(self.clients[clientId]) # TODO 게임 시작 시점에 접속되어 있지 않은 클라이언트 처리

        isValid: bool = game.prepareGame(clients)
        if not isValid :
            errorResponse = self._makeErrorResponse(message, 0, 'GameInfo is invalid.')
            client.messageHandler.send(errorResponse)
            self._clearGame(game)
            return

        game.startGame(self._onGameEnded)

        response = game_pb2.GameStartResponse()
        response.rqid = message.rqid
        client.messageHandler.send(response)

    def _switchClientMessageQuitGame(self, client: ClientHandler, message) :
        if client.clientId not in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            client.messageHandler.send(errorResponse)
            return

        game: GameInstance = self.gameByClientId[client.clientId]
        game.removeClient(client)
        del self.gameByClientId[client.clientId]

        response = game_pb2.QuitGameResponse()
        response.rqid = message.rqid
        client.messageHandler.send(response)

        clientExited = ipc_pb2.ClientExited()
        clientExited.gameId = game.id
        clientExited.clientId = client.clientId
        self.mainProcessMessageHandler.send(clientExited)

    def _switchClientMessageReportChat(self, client: ClientHandler, message) :
        if client.clientId in self.gameByClientId :
            gameId: str = self.gameByClientId[client.clientId].id

            content: dict[str, str] = {}
            content['gameId'] = gameId
            content['reporterId'] = message.reporterId
            content['chatIndex'] = message.chatIndex
            content['comment'] = message.comment

            timestamp: str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            reportId: str = str(uuid.uuid4())
            fileName: str = f'[{timestamp}]_report_{reportId}.json'
            path: str = 'reports'

            os.makedirs(path, exist_ok=True)
            with open(os.path.join(path, fileName), 'w', encoding='utf-8') as file :
                json.dump(content, file, indent=4, ensure_ascii=False)

        response = game_pb2.ReportChatResponse()
        response.rqid = message.rqid
        client.messageHandler.send(response)

    _switchClientMessage = {
        time_pb2.RequestTimeSync : _switchClientMessageRequestTimeSync,
        game_pb2.RequestGameInfo : _switchClientMessageRequestGameInfo,
        game_pb2.GameStart : _switchClientMessageGameStart,
        game_pb2.QuitGame : _switchClientMessageQuitGame,
        game_pb2.ReportChat : _switchClientMessageReportChat,
    }

    def _onGameEnded(self, game: GameInstance) :
        self._clearGame(game)

    def _clearGame(self, game: GameInstance) :
        for clientId in game.clientIds :
            if clientId in self.clients :
                del self.clients[clientId]
            if clientId in self.gameByClientId :
                del self.gameByClientId[clientId]
            # TODO clearSubscribers

        gameEnded = ipc_pb2.GameEnded()
        gameEnded.gameId = game.id
        self.mainProcessMessageHandler.send(gameEnded)

    def _makeErrorResponse(self, message, code: int, detail: str) :
        print(f'[GameProcess] [ERROR] response error message: type={type(message)} code={code}, detail={detail}')
        print(f'[GameProcess] [ERROR] received message: {message}')

        errorResponse = error_pb2.RequestError()
        errorResponse.rqid = message.rqid
        errorResponse.rqtype = messageTypeDict[type(message)]
        errorResponse.code = code
        errorResponse.detail = detail
        return errorResponse

def startGameProcess(port: int) :
    gameProcess = GameProcess(port)
    asyncio.run(gameProcess.run())
