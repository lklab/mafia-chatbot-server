import asyncio
from multiprocessing import Process
import uuid

from game_process import startGameProcess
from client_handler import ClientHandler

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

            # TODO multiplay
            clientInfo = ipc_pb2.Client()
            clientInfo.id = client.clientId
            clientInfo.name = client.clientName
            clients: list[ipc_pb2.Client] = [clientInfo]

            startNewGame = ipc_pb2.StartNewGame()
            startNewGame.gameId = gameId
            startNewGame.clients.extend(clients)

            try :
                await targetProcess.messageHandler.sendAwaitResponse(startNewGame)
            except Exception as e :
                print(f'[MainProcess] startNewGame failed {e}')
                errorResponse = self._makeErrorResponse(message, 0, f'startNewGame failed {e}')
                client.messageHandler.send(errorResponse)
                return

            # assign game
            game: GameHandler = GameHandler(gameId, targetProcess, [client.clientId]) # TODO multiplay
            self.gameDict[gameId] = game
            self.gameByClientId[client.clientId] = game # TODO multiplay

            # response port to client
            newGameResponse = game_pb2.NewGameResponse()
            newGameResponse.rqid = message.rqid
            newGameResponse.port = game.process.port
            client.messageHandler.send(newGameResponse)

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

if __name__ == "__main__" :
    mainProcess = MainProcess()
    asyncio.run(mainProcess.run())
