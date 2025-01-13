from typing import Callable, Any
import asyncio

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.client_handler import ClientHandler
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.message_handler import MessageHandler

from mafia_chatbot.utils.wands_logger import WandsLogger

class ClientServer :
    def __init__(self,
                 port: int,
                 onAuth: Callable[[ClientUser, MessageHandler, Any], tuple[Any, bool]],
                 onMessage: Callable[[ClientHandler, Any], None],
                 onDisconnected: Callable[[ClientHandler], None],
                 logger: WandsLogger,
        ) :
        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected
        self.logger = logger

        self.tcpServer = TcpServer(port)
        self.users: dict[str, ClientUser] = {}

        self._security_connectionCountPerMin: dict[str, int] = {}
        self._security_connectionCountPerMinResetTask = asyncio.create_task(self._security_connectionCountPerMinReset())
        self._security_connectionCount: dict[str, int] = {}

    async def start(self) :
        await self.tcpServer.start(onConnected=self._onConnected)

    async def serve(self) :
        await self.tcpServer.serve()

    def getUser(self, clientId: str, onlyExists: bool = False) :
        if clientId in self.users :
            return self.users[clientId]
        elif not onlyExists :
            user: ClientUser = ClientUser(
                clientId=clientId,
                onRelease=self._onUserRelease,
            )
            self.users[clientId] = user
            return user
        else :
            return None

    def _onConnected(self, tcpHandler: TcpHandler) :
        self.logger.debug(f'[ClientServer] _onConnected() addr={tcpHandler.addr}')

        connectionCountPerMin: int = self._security_connectionCountPerMin.get(tcpHandler.ip, 0)
        if connectionCountPerMin >= 600 :
            asyncio.create_task(tcpHandler.close())
            self.logger.error(f'[ClientServer] _onConnected() addr={tcpHandler.addr} connection was refused due to the limit on the number of connections per minute.')
            return

        connectionCount: int = self._security_connectionCount.get(tcpHandler.ip, 0)
        if connectionCount >= 30 :
            asyncio.create_task(tcpHandler.close())
            self.logger.error(f'[ClientServer] _onConnected() addr={tcpHandler.addr} connection was refused due to the limit on the number of simultaneous connections.')
            return

        self._security_connectionCountPerMin[tcpHandler.ip] = connectionCountPerMin + 1
        self._security_connectionCount[tcpHandler.ip] = connectionCount + 1

        ClientHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onAuth,
            onMessage=self.onMessage,
            onDisconnected=self._onDisconnected,
            logger=self.logger,
        )

    def _onAuth(self, client: ClientHandler, clientId: str, message) -> tuple[Any, ClientUser] :
        self.logger.debug(f'[ClientServer] _onAuth addr={client.addr}, clientId={clientId}')

        # get user
        isUserExists = clientId in self.users
        if isUserExists :
            user: ClientUser = self.users[clientId]
        else :
            user: ClientUser = ClientUser(
                clientId=clientId,
                onRelease=self._onUserRelease,
            )

        # auth by upper layer
        response, success = self.onAuth(user, client.messageHandler, message)

        # success
        if success :
            user.setAuthMethod(message.method)
            if not isUserExists :
                self.users[clientId] = user
            return None, user

        # fail
        else :
            return response, None

    def _onDisconnected(self, client: ClientHandler) :
        self.logger.debug(f'[ClientServer] _onDisconnected() addr={client.addr}')
        ip = client.messageHandler.ip
        connectionCount = self._security_connectionCount[ip]
        if connectionCount > 1 :
            self._security_connectionCount[ip] = connectionCount - 1
        else :
            del self._security_connectionCount[ip]

        self.onDisconnected(client)

    def _onUserRelease(self, user: ClientUser) :
        if user.clientId in self.users :
            del self.users[user.clientId]

    async def _security_connectionCountPerMinReset(self) :
        while True :
            await asyncio.sleep(60)
            self._security_connectionCountPerMin.clear()
