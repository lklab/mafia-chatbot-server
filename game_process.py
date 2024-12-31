import asyncio
import time
import datetime
import uuid
import os
import json
from typing import Callable, Any

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.game_info import GameInfo, DebugInfo

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.client_server import ClientServer
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.utils import makeErrorResponse

import mafia_chatbot.firebase.firebase as firebase

from mafia_chatbot.utils.wands_logger import WandsLogger

MAIN_PROCESS_PORT = 30000

class GameInstance :
    pass

class GameInstance :
    def __init__(self, id: str, users: list[ClientUser], onGameEnded: Callable[[GameInstance], None], logger: WandsLogger) :
        self.id = id

        self.users: dict[str, ClientUser] = {}
        self.clientIds: list[str] = []
        for user in users :
            clientId: str = user.clientId
            self.users[clientId] = user
            self.clientIds.append(clientId)
            user.addRef()

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

    def removeUser(self, user: ClientUser) :
        if user.clientId in self.users :
            if self.gameManager != None :
                self.gameManager.removeUser(user)
            del self.users[user.clientId]

    def terminate(self) :
        self.isTerminated = True

        if self.gameManager != None :
            self.gameManager.terminate()

        for user in self.users.values() :
            user.releaseRef()

        self.onGameEnded(self)

    def _setupGameInfo(self) :
        self.gameInfo = GameInfo(
            gameId=self.id,
            playerCount=self.gameInfoMessage.playerCount,
            mafiaCount=self.gameInfoMessage.mafiaCount,
            users=list(self.users.values()),
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
        self.gameByClientId: dict[str, GameInstance] = {}

        # setup logger
        self.logger = WandsLogger('network', f'game-{self.port}')

    async def run(self) :
        # initialize firebase
        firebase.initialize()

        # start game server
        while True :
            try :
                self.gameServer = ClientServer(
                    port=self.port,
                    onAuth=self._onClientAuth,
                    onMessage=self._onClientMessage,
                    onDisconnected=self._onClientDisconnected,
                )
                await self.gameServer.start()
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
        await self.gameServer.serve()

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

        users: list[ClientUser] = []
        for client in message.clients :
            users.append(self.gameServer.getUser(client.id))

        game: GameInstance = GameInstance(gameId, users, self._clearGame, self.logger)
        for user in users :
            self.gameByClientId[user.clientId] = game

        # send response to main process
        response = ipc_pb2.StartNewGameResponse()
        response.rqid = message.rqid
        self._sendToMainProcess(response)

    _switchMainProcessMessage = {
        ipc_pb2.StartNewGame : _switchMainProcessMessageStartNewGame,
    }

    ### Handle client ###
    def _onClientAuth(self, user: ClientUser, message) -> tuple[Any, bool] :
        self.logger.debug(f'_onClientAuth clientId={user.clientId}')

        if user.clientId in self.gameByClientId :
            return None, True

        else :
            errorResponse = makeErrorResponse(message, 0, 'This server does not contain your game. Please connect to the main server first to create a new game.')
            self.logger.error(f'_onClientAuth failed clientId={user.clientId}, message=<{errorResponse}>')

            return errorResponse, False

    def _onClientMessage(self, user: ClientUser, message) :
        if type(message) != time_pb2.RequestTimeSync :
            self.logger.debug(f'_onClientMessage name={user.clientName}, type={type(message)}, message=<{message}>')

        if type(message) in GameProcess._switchClientMessage :
            GameProcess._switchClientMessage[type(message)](self, user, message)
        else :
            user.forward(message)

    def _onClientDisconnected(self, user: ClientUser) :
        self.logger.debug(f'_onClientDisconnected name={user.clientName}')

    def _switchClientMessageRequestTimeSync(self, user: ClientUser, message) :
        response = time_pb2.TimeSync()
        response.rqid = message.rqid
        response.time = int(time.monotonic() * 1000)
        self._sendToUser(user, response, log=False)

    def _switchClientMessageRequestGameInfo(self, user: ClientUser, message) :
        if user.clientId not in self.gameByClientId :
            errorResponse = makeErrorResponse(message, 0, 'There are no participating games.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        game: GameInstance = self.gameByClientId[user.clientId]
        if game.gameInfoMessage == None :
            errorResponse = makeErrorResponse(message, 0, 'Game info not set yet.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        response = game_pb2.GameInfo()
        response.CopyFrom(game.gameInfoMessage)
        response.rqid = message.rqid
        self._sendToUser(user, response)

    def _switchClientMessageGameStart(self, user: ClientUser, message) :
        if user.clientId not in self.gameByClientId :
            errorResponse = makeErrorResponse(message, 0, 'There are no participating games.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        game: GameInstance = self.gameByClientId[user.clientId]
        if game.isRunning() :
            errorResponse = makeErrorResponse(message, 0, 'The game is already running.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        game.setGameInfoMessage(message.info)

        isValid: bool = game.prepareGame()
        if not isValid :
            errorResponse = makeErrorResponse(message, 0, 'GameInfo is invalid.')
            self._sendToUser(user, errorResponse, isError=True)
            game.terminate()
            return

        game.startGame()

        response = game_pb2.GameStartResponse()
        response.rqid = message.rqid
        self._sendToUser(user, response)

    def _switchClientMessageQuitGame(self, user: ClientUser, message) :
        if user.clientId not in self.gameByClientId :
            errorResponse = makeErrorResponse(message, 0, 'There are no participating games.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        game: GameInstance = self.gameByClientId[user.clientId]
        game.removeUser(user)
        del self.gameByClientId[user.clientId]

        clientExited = ipc_pb2.ClientExited()
        clientExited.gameId = game.id
        clientExited.clientId = user.clientId
        self._sendToMainProcess(clientExited)

        if len(game.clientIds) == 0 :
            game.terminate()

        response = game_pb2.QuitGameResponse()
        response.rqid = message.rqid
        self._sendToUser(user, response)

    def _switchClientMessageReportChat(self, user: ClientUser, message) :
        if user.clientId in self.gameByClientId :
            gameId: str = self.gameByClientId[user.clientId].id

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
        self._sendToUser(user, response)

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

    def _sendToUser(self, user: ClientUser, message, log: bool = True, isError: bool = False) :
        if log :
            if isError :
                self.logger.error(f'_sendToClient id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
            else :
                self.logger.debug(f'_sendToClient id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        user.send(message)

def startGameProcess(port: int) :
    gameProcess = GameProcess(port)
    asyncio.run(gameProcess.run())
