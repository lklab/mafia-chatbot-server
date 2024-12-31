from typing import Callable, Any

from mafia_chatbot.network.tcp_server import TcpServer
from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.client_handler import ClientHandler
from mafia_chatbot.network.client_user import ClientUser

class ClientServer :
    def __init__(self,
                 port: int,
                 onAuth: Callable[[ClientUser, Any], tuple[Any, bool]],
                 onMessage: Callable[[ClientUser, Any], None],
                 onDisconnected: Callable[[ClientUser], None],
        ) :
        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.tcpServer = TcpServer(port)
        self.users: dict[str, ClientUser] = {}

    async def start(self) :
        await self.tcpServer.start(onConnected=self._onConnected)

    async def serve(self) :
        await self.tcpServer.serve()

    def _onConnected(self, tcpHandler: TcpHandler) :
        ClientHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onAuth,
            onMessage=self.onMessage,
            onDisconnected=self.onDisconnected,
        )

    def _onAuth(self, client: ClientHandler, clientId: str, message) -> tuple[Any, ClientUser] :
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
        response, success = self.onAuth(self, clientId, message)

        # success
        if success :
            if not isUserExists :
                self.users[clientId] = user
            return None, user

        # fail
        else :
            return response, None

    def _onUserRelease(self, user: ClientUser) :
        if user.clientId in self.users :
            del self.users[user.clientId]
