import asyncio
from multiprocessing import Process
import uuid
from typing import Any

from game_process import startGameProcess

from mafia_chatbot.main.room_manager import RoomManager
from mafia_chatbot.main.room import Room

from mafia_chatbot.game.game_info import varifyGameInfo

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.client_server import ClientServer
from mafia_chatbot.network.client_user import ClientUser, UserHolder
from mafia_chatbot.network.client_handler import ClientHandler
from mafia_chatbot.network.utils import makeErrorResponse, ErrorCode

from mafia_chatbot.operation.operation_manager import operationManager

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.user_db import userDB
from mafia_chatbot.db.test_account_db import testAccountDB

from mafia_chatbot.utils.wands_logger import WandsLogger
import mafia_chatbot.utils.name_bank as NameBank

GAME_PROCESS_COUNT = 8
MAIN_PORT = 10015
GAME_PORT_FRIST = 10016
GAME_PROCESS_PORT = 30000

class GameHandler(UserHolder) :
    def __init__(self, id: str, users: list[ClientUser], port: int) :
        self.id = id
        self.users = users
        self.port = port

        for user in self.users :
            user.setHolder('gamehandler', self)

    def removeUser(self, user: ClientUser) :
        if user in self.users :
            self.users.remove(user)
            user.releaseHolder('gamehandler')

    def onUserReleased(self, user) :
        self.removeUser(user)

    def terminate(self) :
        for user in self.users :
            user.releaseHolder('gamehandler')
        self.users.clear()

    def updateParticipants(self, message: ipc_pb2.GameParticipant) :
        participants: set[str] = set()
        for participant in message.participants :
            participants.add(participant)

        removeUsers: list[ClientUser] = []
        for user in self.users :
            if user.clientId not in participants :
                removeUsers.append(user)

        for user in removeUsers :
            self.removeUser(user)

class GameProcessHandler :
    def __init__(self, messageHandler: MessageHandler, port: int) :
        self.messageHandler = messageHandler
        self.port = port

        self.games: dict[str, GameHandler] = {}

    def addGame(self, game: GameHandler) :
        if game.id not in self.games :
            self.games[game.id] = game

    def removeGame(self, gameId: str) :
        if gameId in self.games :
            game: GameHandler = self.games[gameId]
            game.terminate()
            del self.games[gameId]

    def getGameCount(self) :
        return len(self.games)

    def setMessageHandler(self, messageHandler: MessageHandler) :
        self.messageHandler = messageHandler

    def isConnected(self) -> bool :
        return self.messageHandler != None

    def updateGames(self, message: ipc_pb2.GameServerConnected) -> list[str] :
        gameIds: set[str] = set()
        for gameParticipant in message.gameParticipants :
            gameIds.add(gameParticipant.gameId)
            self.games[gameParticipant.gameId].updateParticipants(gameParticipant)

        removeGames: list[str] = []
        for gameId in self.games.keys() :
            if gameId not in gameIds :
                removeGames.append(gameId)

        for gameId in removeGames :
            self.removeGame(gameId)

        return removeGames

class MainProcess :
    def __init__(self) :
        self.logger = WandsLogger('network', 'main')

        self.gameProcessHandlers: dict[int, GameProcessHandler] = {}
        self.gameProcessPortDict: dict[MessageHandler, int] = {}
        self.mainServerTask = None

        self.gameToProcessDict: dict[str, GameProcessHandler] = {}

        self.roomManager: RoomManager = RoomManager(self.logger)

    async def run(self) :
        gameProcessServer = TcpServer(port=GAME_PROCESS_PORT, host='127.0.0.1', useSSL=False, trust=True)
        await gameProcessServer.start(onConnected=self._onGameProcessConnected)
        self._startGameProcesses()

        operationManager.initialize()
        NameBank.initialize()
        firebase.initialize()
        userDB.enable_wal()
        testAccountDB.enable_wal()

        await gameProcessServer.serve()

    def _startGameProcesses(self) :
        port: int = GAME_PORT_FRIST
        for _ in range(GAME_PROCESS_COUNT) :
            process = Process(target=startGameProcess, args=(port,))
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
        self.logger.error(f'_onGameProcessDisconnected() addr={messageHandler.addr}, desc={messageHandler.desc}')
        port: int = self.gameProcessPortDict[messageHandler]
        del self.gameProcessPortDict[messageHandler]
        self.gameProcessHandlers[port].setMessageHandler(None)

    def _switchGameProcessMessageGameServerConnected(self, messageHandler: MessageHandler, message) :
        port = message.port
        self.gameProcessPortDict[messageHandler] = port

        if port not in self.gameProcessHandlers :
            handler = GameProcessHandler(messageHandler, port)
            self.gameProcessHandlers[port] = handler
            messageHandler.setDesc(f'{port}')
            self._startMainServer()
        else :
            handler = self.gameProcessHandlers[port]
            handler.setMessageHandler(messageHandler)

            participants: dict[str, list[str]] = {} # TODO delete
            for gameId in handler.games :
                participants[gameId] = [user.clientId for user in self.gameToProcessDict[gameId].games[gameId].users]
            self.logger.debug(f'_switchGameProcessMessageGameServerConnected port={port} game participants(before) = {participants}')

            removedGames: list[str] = handler.updateGames(message)
            for gameId in removedGames :
                if gameId in self.gameToProcessDict :
                    del self.gameToProcessDict[gameId]

        participants: dict[str, list[str]] = {}
        for gameId in handler.games :
            participants[gameId] = [user.clientId for user in self.gameToProcessDict[gameId].games[gameId].users]
        self.logger.debug(f'_switchGameProcessMessageGameServerConnected port={port} game participants(after) = {participants}')

    def _switchGameProcessMessageClientExited(self, messageHandler: MessageHandler, message) :
        user: ClientUser = self.mainServer.getUser(message.clientId, onlyExists=True)
        if user == None :
            return

        game: GameHandler = user.getHolder('gamehandler')
        if game != None :
            game.removeUser(user)

        response = ipc_pb2.ClientExitedResponse()
        response.rqid = message.rqid
        self._sendToGameProcess(messageHandler, response)

    def _switchGameProcessMessageGameEnded(self, messageHandler: MessageHandler, message) :
        gameId: str = message.gameId

        if gameId in self.gameToProcessDict :
            process = self.gameToProcessDict[gameId]
            process.removeGame(gameId)
            del self.gameToProcessDict[gameId]

        response = ipc_pb2.GameEndedResponse()
        response.rqid = message.rqid
        self._sendToGameProcess(messageHandler, response)

    _switchGameProcessMessage = {
        ipc_pb2.GameServerConnected : _switchGameProcessMessageGameServerConnected,
        ipc_pb2.ClientExited : _switchGameProcessMessageClientExited,
        ipc_pb2.GameEnded : _switchGameProcessMessageGameEnded,
    }

    ### Handle client ###
    def _onClientAuth(self, user: ClientUser, messageHandler: MessageHandler, message) -> tuple[Any, bool] :
        self.logger.debug(f'_onClientAuth clientId={user.clientId}')
        return None, True

    def _onClientMessage(self, client: ClientHandler, message) :
        self.logger.debug(f'_onClientMessage clientId={client.user.clientId} name={client.user.clientName}, type={type(message)}, message=<{message}>')
        if type(message) in MainProcess._switchClientMessage :
            MainProcess._switchClientMessage[type(message)](self, client, message)
        else :
            errorResponse = makeErrorResponse(message, ErrorCode.BAD_REQUEST, f'Cannot process the message.')
            self._respondToClient(client, errorResponse, isError=True)

    def _onClientDisconnected(self, client: ClientHandler) :
        if client.user != None :
            self.logger.debug(f'_onClientDisconnected clientId={client.user.clientId} name={client.user.clientName}')

    def _switchClientMessageUpdateUserInfo(self, client: ClientHandler, message) :
        async def _updateInfo() :
            response = await client.user.updateInfo(message)
            self._respondToClient(client, response, isError=isinstance(response, error_pb2.RequestError))

        if not client.user.createTask('updateUserInfo', _updateInfo) :
            errorResponse = makeErrorResponse(message, ErrorCode.BUSY, f'It is already being processed.')
            self._respondToClient(client, errorResponse, isError=True)

    def _switchClientMessageDeleteUser(self, client: ClientHandler, message) :
        try :
            client.user.delete()
        except :
            errorResponse = makeErrorResponse(message, ErrorCode.SERVER_ERROR, 'Fail to delete user')
            self._respondToClient(client, errorResponse, isError=True)
            return

        response = auth_pb2.DeleteUserResponse()
        response.rqid = message.rqid
        self._respondToClient(client, response)

        client.user.disconnect()

    def _switchClientMessageRequestMyRoomInfo(self, client: ClientHandler, message) :
        self.roomManager.processMessageRequestMyRoomInfo(client, message)

    def _switchClientMessageCreateRoom(self, client: ClientHandler, message) :
        # check sign up
        if client.user.isNeedToSignUp() :
            errorResponse = makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'The player has not been fully configured.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        # check current game
        if client.user.getHolder('gamehandler') != None :
            errorResponse = makeErrorResponse(message, ErrorCode.ALREADY_EXISTS, 'The game is already running.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        # check game info
        if not varifyGameInfo(message.gameInfo) :
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The game information is invalid.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        # check human count
        if message.maxHumans > message.gameInfo.playerCount :
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The number of humans cannot exceed the number of players.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        self.roomManager.processMessageCreateRoom(client, message)

    def _switchClientMessageJoinRoom(self, client: ClientHandler, message) :
        # check sign up
        if client.user.isNeedToSignUp() :
            errorResponse = makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'The player has not been fully configured.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        if client.user.getHolder('gamehandler') != None :
            errorResponse = makeErrorResponse(message, ErrorCode.ALREADY_EXISTS, 'The game is already running.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        self.roomManager.processMessageJoinRoom(client, message)

    def _switchClientMessageQuitRoom(self, client: ClientHandler, message) :
        self.roomManager.processMessageQuitRoom(client, message)

    def _switchClientMessageNewGame(self, client: ClientHandler, message) :
        async def _newGame(room: Room) :
            # find free game process
            targetProcess: GameProcessHandler = None
            gameCount: int = 0

            for process in self.gameProcessHandlers.values() :
                if not process.isConnected() :
                    continue

                count = process.getGameCount()
                if targetProcess == None or count < gameCount :
                    targetProcess = process
                    gameCount = count
                if count == 0 :
                    break

            if targetProcess == None :
                errorResponse = makeErrorResponse(message, ErrorCode.SERVER_ERROR, f'Unable to connect to the game process.')
                self._respondToClient(client, errorResponse, isError=True)
                return

            # create new game
            gameId: str = str(uuid.uuid4())

            # setup users
            users: list[ClientUser]
            if room == None :
                users = [client.user]
            else :
                users = room.users

            clients: list[ipc_pb2.Client] = []
            for u in users :
                clientInfo = ipc_pb2.Client()
                clientInfo.id = u.clientId
                clientInfo.name = u.clientName
                clients.append(clientInfo)

            # setup game info
            gameInfo: game_data_pb2.GameInfo = message.gameInfo
            if room != None :
                gameInfo = room.gameInfoRaw

            # send new game
            startNewGame = ipc_pb2.StartNewGame()
            startNewGame.gameId = gameId
            startNewGame.clients.extend(clients)
            startNewGame.gameInfo.CopyFrom(gameInfo)

            try :
                await self._sendAwaitResponseToGameProcess(targetProcess.messageHandler, startNewGame)
            except Exception as e :
                self.logger.error(f'startNewGame failed for {client.user.clientId}: {e}')
                errorResponse = makeErrorResponse(message, ErrorCode.SERVER_ERROR, f'startNewGame failed {e}')
                self._respondToClient(client, errorResponse, isError=True)
                return

            # assign game
            game: GameHandler = GameHandler(gameId, users, targetProcess.port)
            targetProcess.addGame(game)
            self.gameToProcessDict[game.id] = targetProcess

            # destroy room
            if room != None :
                self.roomManager.destroyRoom(room)

            # response port to users
            newGameResponse = room_pb2.NewGameResponse()
            newGameResponse.rqid = message.rqid
            newGameResponse.port = game.port
            self._respondToClient(client, newGameResponse)

            gameStartedMessage = room_pb2.GameStarted()
            gameStartedMessage.port = game.port
            for u in users :
                self._sendToUser(u, gameStartedMessage)

        # check ready
        if client.user.isNeedToSignUp() :
            errorResponse = makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'The player has not been fully configured.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        # check exist game
        if client.user.getHolder('gamehandler') != None :
            errorResponse = makeErrorResponse(message, ErrorCode.ALREADY_EXISTS, 'The game is already running.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        # check room
        room: Room = client.user.getHolder('room')
        if room != None and not room.isHostUser(client.user) :
            errorResponse = makeErrorResponse(message, ErrorCode.NO_PERMISSION, 'You are not the host of the room.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        # check game info
        # 방이 있는 경우 방에 설정된 검증된 game info를 사용
        if room == None and not varifyGameInfo(message.gameInfo) :
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The game information is invalid.')
            self._respondToClient(client, errorResponse, isError=True)
            return

        if not client.user.createTask('newGame', _newGame, room) :
            errorResponse = makeErrorResponse(message, ErrorCode.BUSY, f'It is already being processed.')
            self._respondToClient(client, errorResponse, isError=True)

    def _switchClientMessageCheckCurrentGame(self, client: ClientHandler, message) :
        game: GameHandler = client.user.getHolder('gamehandler')
        if game != None :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = True
            response.port = game.port
            self._respondToClient(client, response)
        else :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = False
            self._respondToClient(client, response)

    _switchClientMessage = {
        auth_pb2.UpdateUserInfo : _switchClientMessageUpdateUserInfo,
        auth_pb2.DeleteUser : _switchClientMessageDeleteUser,
        room_pb2.RequestMyRoomInfo : _switchClientMessageRequestMyRoomInfo,
        room_pb2.CreateRoom : _switchClientMessageCreateRoom,
        room_pb2.JoinRoom : _switchClientMessageJoinRoom,
        room_pb2.QuitRoom : _switchClientMessageQuitRoom,
        room_pb2.NewGame : _switchClientMessageNewGame,
        game_pb2.CheckCurrentGame : _switchClientMessageCheckCurrentGame,
    }

    def _sendToGameProcess(self, messageHandler: MessageHandler, message) :
        self.logger.debug(f'_sendToGameProcess() addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(message)}, message=<{message}>')
        messageHandler.send(message)

    async def _sendAwaitResponseToGameProcess(self, messageHandler: MessageHandler, message) :
        self.logger.debug(f'_sendAwaitResponseToGameProcess() send addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(message)}, message=<{message}>')
        response = await messageHandler.sendAwaitResponse(message)
        self.logger.debug(f'_sendAwaitResponseToGameProcess() response addr={messageHandler.addr}, desc={messageHandler.desc}, type={type(response)}, message=<{response}>')
        return response

    def _respondToClient(self, client: ClientHandler, message, isError: bool = False) :
        if isError :
            self.logger.error(f'_respondToClient id={client.user.clientId}, name={client.user.clientName}, type={type(message)}, message=<{message}>')
        else :
            self.logger.debug(f'_respondToClient id={client.user.clientId}, name={client.user.clientName}, type={type(message)}, message=<{message}>')
        client.respond(message)

    def _sendToUser(self, user: ClientUser, message, isError: bool = False) :
        if isError :
            self.logger.error(f'_sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        else :
            self.logger.debug(f'_sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        user.send(message)

if __name__ == "__main__" :
    mainProcess = MainProcess()
    asyncio.run(mainProcess.run())
