import asyncio
from multiprocessing import Process
import time
import datetime
import uuid
import os
import json

from game_process import startGameProcess
from client_handler import ClientHandler

from mafia_chatbot.game.game_manager import GameManager
from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.game_info import GameInfo, DebugInfo

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

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

    async def run(self) :
        gameProcessServer = TcpServer(port=GAME_PROCESS_PORT, host='127.0.0.1', useSSL=False)
        await gameProcessServer.start(onConnected=self._onGameProcessConnected)
        self._startGameProcesses()
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
        print(f'[MainProcess] _runMainServer')
        mainServer = TcpServer(port=MAIN_PORT)
        await mainServer.start(onConnected=self._onClientConnected)
        await mainServer.serve()

    ### Handle game process ###
    def _onGameProcessConnected(self, tcpHandler: TcpHandler) :
        print(f'[MainProcess] _onGameProcessConnected')
        messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=None,
            onMessage=lambda m: self._onGameProcessMessage(messageHandler, m),
            onDisconnected=lambda: self._onGameProcessDisconnected(messageHandler),
        )

    def _onGameProcessMessage(self, messageHandler: MessageHandler, message) :
        print(f'[MainProcess] _onGameProcessMessage message=<{message}>')
        if type(message) in MainProcess._switchGameProcessMessage :
            MainProcess._switchGameProcessMessage[type(message)](self, messageHandler, message)

    def _onGameProcessDisconnected(self, messageHandler: MessageHandler) :
        print('[MainProcess] _onGameProcessDisconnected') # ERROR!!

    def _switchGameProcessMessageGameServerStarted(self, messageHandler: MessageHandler, message) :
        port = message.port
        handler = GameProcessHandler(messageHandler, port)
        self.gameProcessHandlers.append(handler)
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
            game = self.gameDict[gameId]
            del self.gameDict[gameId]

            for clientId in game.clientIds :
                if clientId in self.gameByClientId :
                    del self.gameByClientId[clientId]

    _switchGameProcessMessage = {
        ipc_pb2.GameServerStarted : _switchGameProcessMessageGameServerStarted,
        ipc_pb2.ClientExited : _switchGameProcessMessageClientExited,
        ipc_pb2.GameEnded : _switchGameProcessMessageGameEnded,
    }

    ### Handle client ###
    def _onClientConnected(self, tcpHandler: TcpHandler) :
        print(f'[MainProcess] _onClientConnected')
        ClientHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
        )

    def _onClientAuth(self, client: ClientHandler, message) :
        print(f'[MainProcess] _onClientAuth name={message.name}, message=<{message}>')
        return True # TODO check auth message

    def _onClientMessage(self, client: ClientHandler, message) :
        print(f'[MainProcess] _onClientMessage name={client.clientName}, message=<{message}>')
        if type(message) in MainProcess._switchClientMessage :
            MainProcess._switchClientMessage[type(message)](self, client, message)
        else :
            errorResponse = self._makeErrorResponse(message, 0, f'Cannot process the message.')
            client.messageHandler.send(errorResponse)

    def _onClientDisconnected(self, client: ClientHandler) :
        print(f'[MainProcess] _onClientDisconnected name={client.clientName}')

    def _switchClientMessageCheckCurrentGame(self, client: ClientHandler, message) :
        if client.clientId in self.gameByClientId :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = True
            response.port = self.gameByClientId[client.clientId].process.port
            client.messageHandler.send(response)
        else :
            response = game_pb2.CurrentGame()
            response.rqid = message.rqid
            response.isGameExists = False
            client.messageHandler.send(response)

    def _switchClientMessageNewGame(self, client: ClientHandler, message) :
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
            clientIds: list[str] = [client.clientId] # TODO multiplay
            startNewGame = ipc_pb2.StartNewGame()
            startNewGame.gameId = gameId
            startNewGame.clients.extend(clientIds)

            try :
                await targetProcess.messageHandler.sendAwaitResponse(startNewGame)
            except Exception as e :
                print(f'[MainProcess] startNewGame failed {e}')
                errorResponse = self._makeErrorResponse(message, 0, f'startNewGame failed {e}')
                client.messageHandler.send(errorResponse)
                return

            # assign game
            game: GameHandler = GameHandler(gameId, targetProcess)
            self.gameDict[gameId] = game
            for clientId in clientIds :
                self.gameByClientId[clientId] = game

            # response port to client
            newGameResponse = game_pb2.NewGameResponse()
            newGameResponse.rqid = message.rqid
            newGameResponse.port = game.process.port

        # check exist game
        if client.clientId in self.gameByClientId :
            errorResponse = self._makeErrorResponse(message, 0, 'The game is already running.')
            client.messageHandler.send(errorResponse)
            return

        asyncio.create_task(_newGame())

    _switchClientMessage = {
        game_pb2.CheckCurrentGame : _switchClientMessageCheckCurrentGame,
        game_pb2.NewGame : _switchClientMessageNewGame,
    }

    def _makeErrorResponse(self, message, code: int, detail: str) :
        print(f'[MainProcess] [ERROR] response error message: type={type(message)} code={code}, detail={detail}')
        print(f'[MainProcess] [ERROR] received message: {message}')

        errorResponse = error_pb2.RequestError()
        errorResponse.rqid = message.rqid
        errorResponse.rqtype = messageTypeDict[type(message)]
        errorResponse.code = code
        errorResponse.detail = detail
        return errorResponse








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
            debugInfo=DebugInfo(gameInfoMessage.debugInfo) if gameInfoMessage.debugInfo.isDebug else None,
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
        server = TcpServer(port=10015)
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

    def _switchMessageRequestTimeSync(self, client: ClientHandler, message) :
        response = time_pb2.TimeSync()
        response.rqid = message.rqid
        response.time = time.monotonic()
        client.messageHandler.send(response)

    def _switchMessageRequestMyGameInfo(self, client: ClientHandler, message) :
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

    def _switchMessageJoinMyGame(self, client: ClientHandler, message) : # TODO delete
        if client.clientId in self.gameDict :
            self.gameDict[client.clientId].manager.assignClient(client.getPlayer())

            response = game_pb2.JoinMyGameResponse()
            response.rqid = message.rqid
            client.messageHandler.send(response)

        else :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            client.messageHandler.send(errorResponse)
            return

    def _switchMessageQuitGame(self, client: ClientHandler, message) :
        if client.clientId in self.gameDict :
            self.gameDict[client.clientId].manager.removeClient(client.getPlayer()) # TODO 아예 나감 처리 해서 종료할지 결정하기
            del self.gameDict[client.clientId]
            client.getPlayer().clearSubscribers()

            response = game_pb2.QuitGameResponse()
            response.rqid = message.rqid
            client.messageHandler.send(response)

        else :
            errorResponse = self._makeErrorResponse(message, 0, 'There are no participating games.')
            client.messageHandler.send(errorResponse)
            return

    def _switchMessageReportChat(self, client: ClientHandler, message) :
        if client.clientId in self.gameDict :
            gameId: str = self.gameDict[client.clientId].manager.gameState.gameId

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

    _switchMessage = {
        time_pb2.RequestTimeSync : _switchMessageRequestTimeSync,
        game_pb2.RequestMyGameInfo : _switchMessageRequestMyGameInfo,
        game_pb2.GameStart : _switchMessageGameStart,
        game_pb2.JoinMyGame : _switchMessageJoinMyGame,
        game_pb2.QuitGame : _switchMessageQuitGame,
        game_pb2.ReportChat : _switchMessageReportChat,
    }

    def _onClientMessage(self, client: ClientHandler, message) :
        if type(message) in MainProgram._switchMessage :
            MainProgram._switchMessage[type(message)](self, client, message)
        else :
            client.getPlayer().forwardMessage(message)

    def _onClientDisconnected(self, client: ClientHandler) :
        if client.clientId in self.gameDict :
            player: ClientPlayer = client.getPlayer()
            self.gameDict[client.clientId].manager.removeClient(player)
            player.clearSubscribers()

    def _makeErrorResponse(self, message, code: int, detail: str) :
        print(f'[MainProgram] [ERROR] response error message: code={code}, detail={detail}')
        print(f'[MainProgram] [ERROR] received message: {message}')

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
            if client.clientId in self.gameDict :
                del self.gameDict[client.clientId]
                client.getPlayer().clearSubscribers()

if __name__ == "__main__" :
    mainProcess = MainProcess()
    asyncio.run(mainProcess.run())
