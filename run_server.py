import asyncio
from multiprocessing import Process
import uuid
from typing import Any

from game_process import startGameProcess

from mafia_chatbot.main.room_manager import RoomManager

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.client_server import ClientServer
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.utils import makeErrorResponse

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.user_db import userDB

from mafia_chatbot.utils.wands_logger import WandsLogger

GAME_PROCESS_COUNT = 8
MAIN_PORT = 10015
GAME_PORT_FRIST = 10016
GAME_PROCESS_PORT = 30000

class GameProcessHandler :
    def __init__(self, messageHandler: MessageHandler, port: int) :
        self.messageHandler = messageHandler
        self.port = port

        self.games: set[str] = set()
        self.gameCount = 0

    def addGame(self, gameId: str) :
        if gameId not in self.games :
            self.games.add(gameId)
            self.gameCount += 1

    def removeGame(self, gameId: str) :
        if gameId in self.games :
            self.games.remove(gameId)
            self.gameCount -= 1

    def getGameCount(self) :
        return self.gameCount

class GameHandler :
    def __init__(self, id: str, process: GameProcessHandler, users: list[ClientUser]) :
        self.id = id
        self.process = process
        self.users = users

        for user in self.users :
            user.setHolder('gamehandler', self)

        process.addGame(id)

    def removeUser(self, user: ClientUser) :
        if user in self.users :
            self.users.remove(user)
            user.releaseHolder('gamehandler')

    def terminate(self) :
        for user in self.users :
            user.releaseHolder('gamehandler')
        self.users.clear()

        self.process.removeGame(self.id)

class MainProcess :
    def __init__(self) :
        self.logger = WandsLogger('network', 'main')

        self.gameProcesses: list[Process] = []
        self.gameProcessHandlers: list[GameProcessHandler] = []
        self.mainServerTask = None

        self.gameDict: dict[str, GameHandler] = {}

        self.roomManager: RoomManager = RoomManager(self.logger)

    async def run(self) :
        gameProcessServer = TcpServer(port=GAME_PROCESS_PORT, host='127.0.0.1', useSSL=False)
        await gameProcessServer.start(onConnected=self._onGameProcessConnected)
        self._startGameProcesses()

        firebase.initialize()
        userDB.enable_wal()

        await gameProcessServer.serve()

    def _startGameProcesses(self) :
        port: int = GAME_PORT_FRIST
        for _ in range(GAME_PROCESS_COUNT) :
            process = Process(target=startGameProcess, args=(port,))
            self.gameProcesses.append(process)
            process.daemon = True
            process.start()
            port += 1

    def _startMainServer(self) :
        if len(self.gameProcessHandlers) == GAME_PROCESS_COUNT and self.mainServerTask == None :
            self.mainServerTask = asyncio.create_task(self._runMainServer())

    async def _runMainServer(self) :
        self.logger.debug('_runMainServer()')
        self.mainServer = ClientServer(
            port=MAIN_PORT,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
            logger=self.logger,
        )
        await self.mainServer.start()
        await self.mainServer.serve()

    ### Handle game process ###
    def _onGameProcessConnected(self, tcpHandler: TcpHandler) :
        self.logger.debug(f'_onGameProcessConnected() addr={tcpHandler.addr}')
        messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=None,
            onMessage=lambda m: self._onGameProcessMessage(messageHandler, m),
            onDisconnected=lambda: self._onGameProcessDisconnected(messageHandler),
        )

    def _onGameProcessMessage(self, messageHandler: MessageHandler, message) :
        self.logger.debug(f'_onGameProcessMessage() addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(message)}, message=<{message}>')
        if type(message) in MainProcess._switchGameProcessMessage :
            MainProcess._switchGameProcessMessage[type(message)](self, messageHandler, message)

    def _onGameProcessDisconnected(self, messageHandler: MessageHandler) :
        self.logger.error(f'[FATAL] _onGameProcessDisconnected() addr={messageHandler.addr}, desc={messageHandler.desc}')

    def _switchGameProcessMessageGameServerStarted(self, messageHandler: MessageHandler, message) :
        port = message.port
        handler = GameProcessHandler(messageHandler, port)
        self.gameProcessHandlers.append(handler)
        messageHandler.setDesc(f'{port}')
        self._startMainServer()

    def _switchGameProcessMessageClientExited(self, messageHandler: MessageHandler, message) :
        user: ClientUser = self.mainServer.getUser(message.clientId, onlyExists=True)
        if user == None :
            return

        game: GameHandler = user.getHolder('gamehandler')
        if game != None :
            game.removeUser(user)

    def _switchGameProcessMessageGameEnded(self, messageHandler: MessageHandler, message) :
        gameId: str = message.gameId

        if gameId in self.gameDict :
            game: GameHandler = self.gameDict[gameId]
            del self.gameDict[gameId]
            game.terminate()

    _switchGameProcessMessage = {
        ipc_pb2.GameServerStarted : _switchGameProcessMessageGameServerStarted,
        ipc_pb2.ClientExited : _switchGameProcessMessageClientExited,
        ipc_pb2.GameEnded : _switchGameProcessMessageGameEnded,
    }

    ### Handle client ###
    def _onClientAuth(self, user: ClientUser, message) -> tuple[Any, bool] :
        self.logger.debug(f'_onClientAuth clientId={user.clientId}')
        return None, True

    def _onClientMessage(self, user: ClientUser, message) :
        self.logger.debug(f'_onClientMessage clientId={user.clientId} name={user.clientName}, type={type(message)}, message=<{message}>')
        if type(message) in MainProcess._switchUserMessage :
            MainProcess._switchUserMessage[type(message)](self, user, message)
        else :
            errorResponse = makeErrorResponse(message, 0, f'Cannot process the message.')
            self._sendToUser(user, errorResponse, isError=True)

    def _onClientDisconnected(self, user: ClientUser) :
        self.logger.debug(f'_onClientDisconnected clientId={user.clientId} name={user.clientName}')

    def _switchUserMessageUpdateUserInfo(self, user: ClientUser, message) :
        async def _updateInfo() :
            response = await user.updateInfo(message)
            self._sendToUser(user, response, isError=isinstance(response, error_pb2.RequestError))

        asyncio.create_task(_updateInfo()) # TODO 중복 호출에 대한 처리

    def _switchUserMessageDeleteUser(self, user: ClientUser, message) :
        user.delete()

        response = auth_pb2.DeleteUserResponse()
        response.rqid = message.rqid
        self._sendToUser(user, response)

        user.disconnect()

    def _switchUserMessageRequestMyRoomInfo(self, user: ClientUser, message) :
        self.roomManager.processMessageRequestMyRoomInfo(user, message)

    def _switchUserMessageCreateRoom(self, user: ClientUser, message) :
        if user.getHolder('gamehandler') != None :
            errorResponse = makeErrorResponse(message, 0, 'The game is already running.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        self.roomManager.processMessageCreateRoom(user, message)

    def _switchUserMessageJoinRoom(self, user: ClientUser, message) :
        if user.getHolder('gamehandler') != None :
            errorResponse = makeErrorResponse(message, 0, 'The game is already running.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        self.roomManager.processMessageJoinRoom(user, message)

    def _switchUserMessageQuitRoom(self, user: ClientUser, message) :
        self.roomManager.processMessageQuitRoom(user, message)

    def _switchUserMessageNewGame(self, user: ClientUser, message) :
        async def _newGame() :
            # find free game process
            targetProcess: GameProcessHandler = None
            gameCount: int = 0
            
            for process in self.gameProcessHandlers :
                count = process.getGameCount()
                if targetProcess == None or count < gameCount :
                    targetProcess = process
                    gameCount = count
                if count == 0 :
                    break

            # send new game
            gameId: str = str(uuid.uuid4())

            # TODO multiplay
            clientInfo = ipc_pb2.Client()
            clientInfo.id = user.clientId
            clientInfo.name = user.clientName
            clients: list[ipc_pb2.Client] = [clientInfo]

            startNewGame = ipc_pb2.StartNewGame()
            startNewGame.gameId = gameId
            startNewGame.clients.extend(clients)

            try :
                await self._sendAwaitResponseToGameProcess(targetProcess.messageHandler, startNewGame)
            except Exception as e :
                self.logger.error(f'startNewGame failed for {user.clientId}: {e}')
                errorResponse = makeErrorResponse(message, 0, f'startNewGame failed {e}')
                self._sendToUser(user, errorResponse, isError=True)
                return

            # assign game
            game: GameHandler = GameHandler(gameId, targetProcess, [user]) # TODO multiplay
            self.gameDict[gameId] = game

            # response port to client
            newGameResponse = game_pb2.NewGameResponse()
            newGameResponse.rqid = message.rqid
            newGameResponse.port = game.process.port
            self._sendToUser(user, newGameResponse)

        # check ready
        if user.isNeedToSignUp() :
            errorResponse = makeErrorResponse(message, 0, 'The player has not been fully configured.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        # check exist game
        if user.getHolder('gamehandler') != None :
            errorResponse = makeErrorResponse(message, 0, 'The game is already running.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        asyncio.create_task(_newGame()) # TODO 중복 호출에 대한 처리

    def _switchUserMessageCheckCurrentGame(self, user: ClientUser, message) :
        game: GameHandler = user.getHolder('gamehandler')
        if game != None :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = True
            response.port = game.process.port
            self._sendToUser(user, response)
        else :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = False
            self._sendToUser(user, response)

    _switchUserMessage = {
        auth_pb2.UpdateUserInfo : _switchUserMessageUpdateUserInfo,
        auth_pb2.DeleteUser : _switchUserMessageDeleteUser,
        room_pb2.RequestMyRoomInfo : _switchUserMessageRequestMyRoomInfo,
        room_pb2.CreateRoom : _switchUserMessageCreateRoom,
        room_pb2.JoinRoom : _switchUserMessageJoinRoom,
        room_pb2.QuitRoom : _switchUserMessageQuitRoom,
        room_pb2.NewGame : _switchUserMessageNewGame,
        game_pb2.CheckCurrentGame : _switchUserMessageCheckCurrentGame,
    }

    def _sendToGameProcess(self, messageHandler: MessageHandler, message) :
        self.logger.debug(f'_sendToGameProcess() addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(message)}, message=<{message}>')
        messageHandler.send(message)

    async def _sendAwaitResponseToGameProcess(self, messageHandler: MessageHandler, message) :
        self.logger.debug(f'_sendAwaitResponseToGameProcess() send addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(message)}, message=<{message}>')
        response = await messageHandler.sendAwaitResponse(message)
        self.logger.debug(f'_sendAwaitResponseToGameProcess() response addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(response)}, message=<{response}>')
        return response

    def _sendToUser(self, user: ClientUser, message, isError: bool = False) :
        if isError :
            self.logger.error(f'_sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        else :
            self.logger.debug(f'_sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        user.send(message)

if __name__ == "__main__" :
    mainProcess = MainProcess()
    asyncio.run(mainProcess.run())
