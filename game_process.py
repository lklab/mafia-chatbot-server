import asyncio
import time
import datetime
import uuid
import os
import json
from typing import Callable, Any

from client_handler import ClientHandler

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.game_info import GameInfo, DebugInfo
from mafia_chatbot.game.client_player import ClientPlayer

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

from mafia_chatbot.utils.wands_logger import WandsLogger

MAIN_PROCESS_PORT = 30000

class GameInstance :
    pass

class GameInstance :
    def __init__(self, id: str, players: list[ClientPlayer], onGameEnded: Callable[[GameInstance], None], logger: WandsLogger) :
        self.id = id

        self.players: dict[str, ClientPlayer] = {}
        self.clientIds: list[str] = []
        for player in players :
            clientId: str = player.clientId
            self.players[clientId] = player
            self.clientIds.append(clientId)

        self.onGameEnded = onGameEnded

        self.logger = logger

        self.gameInfoMessage: game_pb2.GameInfo = None
        self.gameInfo: GameInfo = None

        self.gameManager: GameManager = None
        self.isTerminated: bool = False

        self.timeoutTask = asyncio.create_task(self._timeoutTerminate(60))

    def setGameInfoMessage(self, message: game_pb2.GameInfo) :
        self.gameInfoMessage = message

    def prepareGame(self) -> bool :
        if self.gameManager != None or self.isTerminated :
            return False
        self._setupGameInfo()
        return self.gameInfo.checkValid()

    def startGame(self) :
        async def _startGame() :
            await self.gameManager.start()
            self.terminate()

        if self.gameManager != None or self.gameInfo == None or self.isTerminated :
            return

        self.timeoutTask.cancel()
        self.gameManager = GameManager(self.gameInfo)
        asyncio.create_task(_startGame())

    def isRunning(self) :
        return self.gameManager != None

    def connectClient(self, clientId: str, messageHandler: MessageHandler) :
        if clientId in self.players :
            self.players[clientId].setMessageHandler(messageHandler)

    def disconnectClient(self, clientId: str) :
        if clientId in self.players :
            self.players[clientId].clearMessageHandler()

    def removeClient(self, clientId: str) :
        if clientId in self.players :
            self.players[clientId].clearMessageHandler()
            self.players[clientId].clearSubscribers()
            del self.players[clientId]

    def getPlayer(self, clientId: str) -> ClientPlayer :
        if clientId in self.players :
            return self.players[clientId]
        else :
            return None

    def terminate(self) :
        self.isTerminated = True

        if self.gameManager != None :
            self.gameManager.terminate()

        for player in self.players.values() :
            player.clearMessageHandler()
            player.clearSubscribers()
        self.players.clear()

        self.onGameEnded(self)

    def _setupGameInfo(self) :
        self.gameInfo = GameInfo(
            gameId=self.id,
            playerCount=self.gameInfoMessage.playerCount,
            mafiaCount=self.gameInfoMessage.mafiaCount,
            clients=list(self.players.values()),
            localPlayerName=None,
            language=self.gameInfoMessage.language,
            debugInfo=DebugInfo(self.gameInfoMessage.debugInfo) if self.gameInfoMessage.debugInfo.isDebug else None,
        )

    async def _timeoutTerminate(self, seconds: float) :
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError :
            return

        self.logger.error(f'game {self.id} terminated by timeout')
        self.terminate()

class GameProcess :
    def __init__(self, port: int) :
        self.port: int = port

        self.clients: dict[str, ClientHandler] = {}
        self.gameByClientId: dict[str, GameInstance] = {}

        # setup logger
        self.logger = WandsLogger('network', f'game-{self.port}')

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
        message = ipc_pb2.GameServerStarted()
        message.port = self.port
        self._sendToMainProcess(message)

        # serve game server
        await gameServer.serve()

    ### Handle main process ###
    def _onMainProcessMessage(self, message) :
        self.logger.debug(f'_onMainProcessMessage() type={type(message)}, message=<{message}>')
        if type(message) in GameProcess._switchMainProcessMessage :
            GameProcess._switchMainProcessMessage[type(message)](self, message)

    def _onMainProcessDisconnected(self) :
        self.logger.error(f'[FATAL] _onMainProcessDisconnected()')

    def _switchMainProcessMessageStartNewGame(self, message) :
        # prepare game
        gameId: str = message.gameId

        players: list[ClientPlayer] = []
        for client in message.clients :
            players.append(ClientPlayer(client.id, client.name))

        game: GameInstance = GameInstance(gameId, players, self._clearGame, self.logger)
        for player in players :
            self.gameByClientId[player.clientId] = game

        # send response to main process
        response = ipc_pb2.StartNewGameResponse()
        response.rqid = message.rqid
        self._sendToMainProcess(response)

    _switchMainProcessMessage = {
        ipc_pb2.StartNewGame : _switchMainProcessMessageStartNewGame,
    }

    ### Handle client ###
    def _onClientConnected(self, tcpHandler: TcpHandler) :
        self.logger.debug(f'_onClientConnected() addr={tcpHandler.addr}')
        ClientHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
        )

    async def _onClientAuth(self, client: ClientHandler, message) -> tuple[Any, bool] :
        self.logger.debug(f'_onClientAuth addr={client.addr}, message=<{message}>')
        clientId: str = message.clientId

        if clientId in self.gameByClientId :
            self.clients[clientId] = client

            game: GameInstance = self.gameByClientId[clientId]
            game.connectClient(clientId, client.messageHandler)
            client.setPlayer(game.getPlayer(clientId))

            return auth_pb2.AuthResponse(), True
        else :
            errorResponse = self._makeErrorResponse(message, 0, 'This server does not contain your game. Please connect to the main server first to create a new game.')
            self.logger.error(f'_onClientAuth failed addr={client.addr}, message=<{errorResponse}>')
            return errorResponse, False

    def _onClientMessage(self, client: ClientHandler, message) :
        self.logger.debug(f'_onClientMessage addr={client.addr}, name={client.clientName}, type={type(message)}, message=<{message}>')
        if type(message) in GameProcess._switchClientMessage :
            GameProcess._switchClientMessage[type(message)](self, client, message)
        else :
            client.forwardMessage(message)

    def _onClientDisconnected(self, client: ClientHandler) :
        self.logger.debug(f'_onClientDisconnected addr={client.addr}, name={client.clientName}')
        if client.clientId in self.clients :
            del self.clients[client.clientId]
        if client.clientId in self.gameByClientId :
            game: GameInstance = self.gameByClientId[client.clientId]
            game.disconnectClient(client.clientId)

    def _switchClientMessageRequestTimeSync(self, client: ClientHandler, message) :
        response = time_pb2.TimeSync()
        response.rqid = message.rqid
        response.time = time.monotonic()
        self._sendToClient(client, response)

    def _switchClientMessageRequestGameInfo(self, client: ClientHandler, message) :
        if client.clientId not in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            self._sendToClient(client, errorResponse, isError=True)
            return

        game: GameInstance = self.gameByClientId[client.clientId]
        if game.gameInfoMessage == None :
            errorResponse = self._makeErrorResponse(message, 0, 'Game info not set yet.')
            self._sendToClient(client, errorResponse, isError=True)
            return

        response = game_pb2.GameInfo()
        response.CopyFrom(game.gameInfoMessage)
        response.rqid = message.rqid
        self._sendToClient(client, response)

    def _switchClientMessageGameStart(self, client: ClientHandler, message) :
        if client.clientId not in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            self._sendToClient(client, errorResponse, isError=True)
            return

        game: GameInstance = self.gameByClientId[client.clientId]
        if game.isRunning() :
            errorResponse = self._makeErrorResponse(message, 0, 'The game is already running.')
            self._sendToClient(client, errorResponse, isError=True)
            return

        game.setGameInfoMessage(message.info)

        isValid: bool = game.prepareGame()
        if not isValid :
            errorResponse = self._makeErrorResponse(message, 0, 'GameInfo is invalid.')
            self._sendToClient(client, errorResponse, isError=True)
            game.terminate()
            return

        game.startGame()

        response = game_pb2.GameStartResponse()
        response.rqid = message.rqid
        self._sendToClient(client, response)

    def _switchClientMessageQuitGame(self, client: ClientHandler, message) :
        if client.clientId not in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            self._sendToClient(client, errorResponse, isError=True)
            return

        game: GameInstance = self.gameByClientId[client.clientId]
        game.removeClient(client.clientId)
        del self.gameByClientId[client.clientId]

        clientExited = ipc_pb2.ClientExited()
        clientExited.gameId = game.id
        clientExited.clientId = client.clientId
        self._sendToMainProcess(clientExited)

        if len(game.clientIds) == 0 :
            game.terminate()

        response = game_pb2.QuitGameResponse()
        response.rqid = message.rqid
        self._sendToClient(client, response)

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
        self._sendToClient(client, response)

    _switchClientMessage = {
        time_pb2.RequestTimeSync : _switchClientMessageRequestTimeSync,
        game_pb2.RequestGameInfo : _switchClientMessageRequestGameInfo,
        game_pb2.GameStart : _switchClientMessageGameStart,
        game_pb2.QuitGame : _switchClientMessageQuitGame,
        game_pb2.ReportChat : _switchClientMessageReportChat,
    }

    def _clearGame(self, game: GameInstance) :
        for clientId in game.clientIds :
            if clientId in self.gameByClientId :
                del self.gameByClientId[clientId]

        gameEnded = ipc_pb2.GameEnded()
        gameEnded.gameId = game.id
        self._sendToMainProcess(gameEnded)

    def _sendToMainProcess(self, message) :
        self.logger.debug(f'_sendToMainProcess() type={type(message)}, message=<{message}>')
        self.mainProcessMessageHandler.send(message)

    async def _sendAwaitResponseToMainProcess(self, message) :
        self.logger.debug(f'_sendAwaitResponseToMainProcess() send type={type(message)}, message=<{message}>')
        response = await self.mainProcessMessageHandler.sendAwaitResponse(message)
        self.logger.debug(f'_sendAwaitResponseToMainProcess() response type={type(response)}, message=<{response}>')
        return response

    def _sendToClient(self, client: ClientHandler, message, isError: bool = False) :
        if isError :
            self.logger.error(f'_sendToClient addr={client.addr}, name={client.clientName}, type={type(message)}, message=<{message}>')
        else :
            self.logger.debug(f'_sendToClient addr={client.addr}, name={client.clientName}, type={type(message)}, message=<{message}>')
        client.messageHandler.send(message)

    def _makeErrorResponse(self, message, code: int, detail: str) :
        errorResponse = error_pb2.RequestError()
        errorResponse.rqid = message.rqid
        errorResponse.rqtype = messageTypeDict[type(message)]
        errorResponse.code = code
        errorResponse.detail = detail
        return errorResponse

def startGameProcess(port: int) :
    gameProcess = GameProcess(port)
    asyncio.run(gameProcess.run())
