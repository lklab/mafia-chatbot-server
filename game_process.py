import asyncio
import time
import datetime
import uuid
import os
import json
import gc
from typing import Callable, Awaitable, Any

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.game_info import GameInfo, DebugInfo
from mafia_chatbot.game.player_info import protoToRoleDict

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.client_server import ClientServer
from mafia_chatbot.network.client_user import ClientUser, UserHolder
from mafia_chatbot.network.client_handler import ClientHandler
from mafia_chatbot.network.utils import makeErrorResponse, ErrorCode

from mafia_chatbot.operation.operation_manager import operationManager

import mafia_chatbot.firebase.firebase as firebase

from mafia_chatbot.utils.wands_logger import WandsLogger
import mafia_chatbot.utils.name_bank as NameBank
import mafia_chatbot.utils.server_config as server_config

class GameInstance :
    pass

class GameInstance(UserHolder) :
    def __init__(self,
                 id: str,
                 users: list[ClientUser],
                 gameInfoRaw: game_data_pb2.GameInfo,
                 onGameEnded: Callable[[GameInstance], Awaitable[None]],
                 logger: WandsLogger
    ) :
        self.id = id
        self.gameInfoRaw = gameInfoRaw
        self.onGameEnded = onGameEnded
        self.logger = logger
        self.isTerminated: bool = False

        self.users: dict[str, ClientUser] = {}
        for user in users :
            self.users[user.clientId] = user
            user.setHolder('game', self)
        self.readyUsers: set[str] = set()

        self.gameManager: GameManager = None

        self.timeoutTask = asyncio.create_task(self._timeoutTerminate(60))

    def readyUser(self, user: ClientUser) :
        if user.clientId in self.users and user.clientId not in self.readyUsers :
            self.readyUsers.add(user.clientId)
            self._checkUserState()

    def removeUser(self, user: ClientUser) :
        if user.clientId in self.users :
            if self.gameManager != None :
                self.gameManager.removeUser(user)

            user.releaseHolder('game')

            del self.users[user.clientId]
            self.readyUsers.discard(user.clientId)

            self._checkUserState()

    # override
    def onUserReleased(self, user) :
        self.removeUser(user)

    def isRunning(self) :
        return self.gameManager != None

    def _checkUserState(self) :
        # 남은 사용자가 없는 경우 게임 종료
        if len(self.users) == 0 :
            self._terminate()

        # 모든 플레이어가 준비된 경우 게임 시작
        elif len(self.users) == len(self.readyUsers) :
            self._startGame()

    def _startGame(self) :
        async def _startGame() :
            await self.gameManager.start()
            self._terminate()

        # 이미 게임이 시작된 경우, 종료된 경우 무시
        if self.gameManager != None or self.isTerminated :
            return

        # stop timeout
        self.timeoutTask.cancel()

        # create game
        gameInfo: GameInfo = GameInfo(
            gameId=self.id,
            playerCount=self.gameInfoRaw.playerCount,
            mafiaCount=self.gameInfoRaw.mafiaCount,
            users=list(self.users.values()),
            localPlayerName=None,
            language=self.gameInfoRaw.language,
            fixedRole = protoToRoleDict[self.gameInfoRaw.fixedRole],
            debugInfo=DebugInfo(self.gameInfoRaw.debugInfo) if self.gameInfoRaw.debugInfo.isDebug else None,
        )
        self.gameManager = GameManager(gameInfo)

        # start game logic
        asyncio.create_task(_startGame())

    def _terminate(self) :
        if self.isTerminated :
            return
        self.isTerminated = True
        asyncio.create_task(self._terminateAsync())

    async def _terminateAsync(self) :
        if self.gameManager != None :
            self.gameManager.terminate()

        for user in self.users.values() :
            user.releaseHolder('game')

        # 메인 프로세스에서 게임 종료 처리될 때까지 대기
        await self.onGameEnded(self)

        if self.gameManager != None :
            self.gameManager.sendGameEndToUsers()

        collected = gc.collect()

    async def _timeoutTerminate(self, seconds: float) :
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError :
            return

        self.logger.error(f'game {self.id} terminated by timeout')
        self._terminate()

class GameProcess :
    def __init__(self, port: int) :
        self.port: int = port
        self.games: dict[str, GameInstance] = {}

        # setup logger
        self.logger = WandsLogger('network_log', f'game-{self.port}')

    async def run(self) :
        # initialize
        NameBank.initialize()
        firebase.initialize()
        operationManager.initialize()

        # start game server
        while True :
            try :
                self.gameServer = ClientServer(
                    port=self.port,
                    onAuth=self._onClientAuth,
                    onMessage=self._onClientMessage,
                    onDisconnected=self._onClientDisconnected,
                    logger=self.logger,
                )
                await self.gameServer.start()
            except OSError as e :
                self.port += 1
                await asyncio.sleep(0.3)
                continue
            break

        # connect to main process
        await self._connectToMainProcess()

        # serve game server
        await self.gameServer.serve()

    ### Handle main process ###
    async def _connectToMainProcess(self) :
        # connect to main process
        reader, writer = await asyncio.open_connection('127.0.0.1', server_config.getIpcPort())
        mainProcessTcpHandler = TcpHandler(reader, writer, trust=True)
        self.mainProcessMessageHandler = MessageHandler(
            tcpHandler=mainProcessTcpHandler,
            onAuth=None,
            onMessage=self._onMainProcessMessage,
            onDisconnected=self._onMainProcessDisconnected,
        )
        self.logger.debug(f'_connectToMainProcess() connected to main process')

        # send GameServerConnected message to main process
        message = self._makeGameServerConnectedMessage()
        self._sendToMainProcess(message)

    def _makeGameServerConnectedMessage(self) -> ipc_pb2.GameServerConnected :
        message = ipc_pb2.GameServerConnected()
        message.port = self.port

        gameParticipants: list[ipc_pb2.GameParticipant] = []
        for game in self.games.values() :
            gameParticipant = ipc_pb2.GameParticipant()
            gameParticipant.gameId = game.id
            gameParticipant.participants.extend([user for user in game.users.keys()])
            gameParticipants.append(gameParticipant)
        message.gameParticipants.extend(gameParticipants)

        return message

    def _onMainProcessMessage(self, message) :
        self.logger.debug(f'_onMainProcessMessage() type={type(message)}, message=<{message}>')
        if type(message) in GameProcess._switchMainProcessMessage :
            GameProcess._switchMainProcessMessage[type(message)](self, message)

    def _onMainProcessDisconnected(self) :
        self.logger.error(f'_onMainProcessDisconnected()')
        self.mainProcessMessageHandler = None
        asyncio.create_task(self._connectToMainProcess())

    def _switchMainProcessMessageStartNewGame(self, message) :
        # prepare game
        gameId: str = message.gameId

        users: list[ClientUser] = []
        for client in message.clients :
            users.append(self.gameServer.getUser(client.id))

        game: GameInstance = GameInstance(gameId, users, message.gameInfo, self._clearGame, self.logger)
        self.games[gameId] = game

        # send response to main process
        response = ipc_pb2.StartNewGameResponse()
        response.rqid = message.rqid
        self._sendToMainProcess(response)

    def _switchMainProcessMessageRestartServer(self, message) :
        async def restart() :
            await asyncio.sleep(60)
            await self.gameServer.restart()

            response = ipc_pb2.ServerRestarted()
            response.rqid = message.rqid
            self._sendToMainProcess(response)

        asyncio.create_task(restart())

    _switchMainProcessMessage = {
        ipc_pb2.StartNewGame : _switchMainProcessMessageStartNewGame,
        ipc_pb2.RestartServer : _switchMainProcessMessageRestartServer,
    }

    ### Handle client ###
    def _onClientAuth(self, user: ClientUser, messageHandler: MessageHandler, message) -> tuple[Any, bool] :
        self.logger.debug(f'_onClientAuth clientId={user.clientId}')

        if user.getHolder('game') != None :
            return None, True

        else :
            errorResponse = makeErrorResponse(message, ErrorCode.NOT_FOUND, 'This server does not contain your game. Please connect to the main server first to create a new game.')
            self.logger.error(f'_onClientAuth failed clientId={user.clientId}, message=<{errorResponse}>')

            return errorResponse, False

    def _onClientMessage(self, client: ClientHandler, message) :
        if type(message) != time_pb2.RequestTimeSync :
            self.logger.debug(f'_onClientMessage clientId={client.user.clientId} name={client.user.clientName}, type={type(message)}, message=<{message}>')

        if type(message) in GameProcess._switchClientMessage :
            GameProcess._switchClientMessage[type(message)](self, client, message)
        else :
            if client.user.forward(client.messageHandler, message) :
                pass
            else :
                errorResponse = makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Cannot process the message.')
                self._respondToClient(client, errorResponse, isError=True)
                return

    def _onClientDisconnected(self, client: ClientHandler) :
        if client.user != None :
            self.logger.debug(f'_onClientDisconnected clientId={client.user.clientId} name={client.user.clientName}')

    def _switchClientMessageRequestTimeSync(self, client: ClientHandler, message) :
        response = time_pb2.TimeSync()
        response.rqid = message.rqid
        response.time = int(time.monotonic() * 1000)
        self._respondToClient(client, response, log=False)

    def _switchClientMessageRequestCurrentGameInfo(self, client: ClientHandler, message) :
        game: GameInstance = client.user.getHolder('game')
        if game == None :
            errorResponse = makeErrorResponse(message, ErrorCode.NOT_FOUND, 'There are no participating games.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        response = game_pb2.CurrentGameInfo()
        response.rqid = message.rqid
        response.info.CopyFrom(game.gameInfoRaw)
        self._respondToClient(client, response)

    def _switchClientMessageReadyGame(self, client: ClientHandler, message) :
        game: GameInstance = client.user.getHolder('game')
        if game == None :
            errorResponse = makeErrorResponse(message, ErrorCode.NOT_FOUND, 'There are no participating games.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        game.readyUser(client.user)

        response = game_pb2.ReadyGameResponse()
        response.rqid = message.rqid
        self._respondToClient(client, response)

    def _switchClientMessageQuitGame(self, client: ClientHandler, message) :
        async def _quitGame(game: GameInstance) :
            clientExited = ipc_pb2.ClientExited()
            clientExited.gameId = game.id
            clientExited.clientId = client.user.clientId

            try :
                await self._sendAwaitResponseToMainProcess(clientExited)
            except Exception as e :
                self.logger.error(f'clientExited failed for {client.user.clientId}: {e}')

            # 남은 사용자가 없는 경우 terminate에서 _clearGame이 호출되는데
            # ClientExited를 GameEnded보다 먼저 보내야 하므로 이 위치에 있어야 함
            game.removeUser(client.user)

            response = game_pb2.QuitGameResponse()
            response.rqid = message.rqid
            self._respondToClient(client, response)

        game: GameInstance = client.user.getHolder('game')
        if game == None :
            errorResponse = makeErrorResponse(message, ErrorCode.NOT_FOUND, 'There are no participating games.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        if not client.user.createTask('quitGame', _quitGame, game) :
            errorResponse = makeErrorResponse(message, ErrorCode.BUSY, f'It is already being processed.')
            self._respondToClient(client, errorResponse, isError=True)

    def _switchClientMessageReportChat(self, client: ClientHandler, message) :
        game: GameInstance = client.user.getHolder('game')
        if game != None :
            gameId: str = game.id

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
        self._respondToClient(client, response)

    _switchClientMessage = {
        time_pb2.RequestTimeSync : _switchClientMessageRequestTimeSync,
        game_pb2.RequestCurrentGameInfo : _switchClientMessageRequestCurrentGameInfo,
        game_pb2.ReadyGame : _switchClientMessageReadyGame,
        game_pb2.QuitGame : _switchClientMessageQuitGame,
        game_pb2.ReportChat : _switchClientMessageReportChat,
    }

    async def _clearGame(self, game: GameInstance) :
        del self.games[game.id]

        gameEnded = ipc_pb2.GameEnded()
        gameEnded.gameId = game.id

        try :
            await self._sendAwaitResponseToMainProcess(gameEnded)
        except Exception as e :
            self.logger.error(f'gameEnded failed for {game.id}: {e}')

    def _sendToMainProcess(self, message) :
        self.logger.debug(f'_sendToMainProcess() type={type(message)}, message=<{message}>')
        if self.mainProcessMessageHandler != None :
            self.mainProcessMessageHandler.send(message)

    async def _sendAwaitResponseToMainProcess(self, message) :
        self.logger.debug(f'_sendAwaitResponseToMainProcess() send type={type(message)}, message=<{message}>')
        if self.mainProcessMessageHandler != None :
            response = await self.mainProcessMessageHandler.sendAwaitResponse(message)
        else :
            raise Exception('Main process is not connected')
        self.logger.debug(f'_sendAwaitResponseToMainProcess() response type={type(response)}, message=<{response}>')
        return response

    def _respondToClient(self, client: ClientHandler, message, log: bool = True, isError: bool = False) :
        if log :
            if isError :
                self.logger.error(f'_respondToClient id={client.user.clientId}, name={client.user.clientName}, type={type(message)}, message=<{message}>')
            else :
                self.logger.debug(f'_respondToClient id={client.user.clientId}, name={client.user.clientName}, type={type(message)}, message=<{message}>')
        client.respond(message)

    def _sendToUser(self, user: ClientUser, message, log: bool = True, isError: bool = False) :
        if log :
            if isError :
                self.logger.error(f'_sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
            else :
                self.logger.debug(f'_sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        user.send(message)

def startGameProcess(port: int) :
    gameProcess = GameProcess(port)
    asyncio.run(gameProcess.run())
