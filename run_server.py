import asyncio
from multiprocessing import Process
import uuid
from typing import Any

from game_process import startGameProcess

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
    def __init__(self, id: str, process: GameProcessHandler, clientIds: list[str]) :
        self.id = id
        self.process = process
        self.clientIds = clientIds

        process.addGame(id)

    def removeClient(self, clientId: str) :
        self.clientIds.remove(clientId)

    def terminate(self) :
        self.process.removeGame(self.id)

class MainProcess :
    def __init__(self) :
        self.gameProcesses: list[Process] = []
        self.gameProcessHandlers: list[GameProcessHandler] = []
        self.mainServerTask = None

        self.gameDict: dict[str, GameHandler] = {}
        self.gameByClientId: dict[str, GameHandler] = {}

        # setup logger
        self.logger = WandsLogger('network', 'main')

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
        mainServer = ClientServer(
            port=MAIN_PORT,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
            logger=self.logger,
        )
        await mainServer.start()
        await mainServer.serve()

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
        # gameId: str = message.gameId
        clientId: str = message.clientId

        if clientId in self.gameByClientId :
            game: GameHandler = self.gameByClientId[clientId]
            game.removeClient(clientId)
            del self.gameByClientId[clientId]

    def _switchGameProcessMessageGameEnded(self, messageHandler: MessageHandler, message) :
        gameId: str = message.gameId

        if gameId in self.gameDict :
            game: GameHandler = self.gameDict[gameId]
            del self.gameDict[gameId]
            game.terminate()

            for clientId in game.clientIds :
                if clientId in self.gameByClientId :
                    del self.gameByClientId[clientId]

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

    def _switchUserMessageCheckCurrentGame(self, user: ClientUser, message) :
        if user.clientId in self.gameByClientId :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = True
            response.port = self.gameByClientId[user.clientId].process.port
            self._sendToUser(user, response)
        else :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = False
            self._sendToUser(user, response)

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
            game: GameHandler = GameHandler(gameId, targetProcess, [user.clientId]) # TODO multiplay
            self.gameDict[gameId] = game
            self.gameByClientId[user.clientId] = game # TODO multiplay

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
        if user.clientId in self.gameByClientId :
            errorResponse = makeErrorResponse(message, 0, 'The game is already running.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        asyncio.create_task(_newGame()) # TODO 중복 호출에 대한 처리

    _switchUserMessage = {
        auth_pb2.UpdateUserInfo : _switchUserMessageUpdateUserInfo,
        auth_pb2.DeleteUser : _switchUserMessageDeleteUser,
        game_pb2.CheckCurrentGame : _switchUserMessageCheckCurrentGame,
        game_pb2.NewGame : _switchUserMessageNewGame,
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
            self.logger.debug(f'_sendToClient id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        user.send(message)

if __name__ == "__main__" :
    mainProcess = MainProcess()
    asyncio.run(mainProcess.run())
