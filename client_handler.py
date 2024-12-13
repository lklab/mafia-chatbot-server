from typing import Callable, Any

from mafia_chatbot.game.client_player import ClientPlayer

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler

class ClientHandler :
    pass

class ClientHandler :
    def __init__(self,
                 tcpHandler: TcpHandler,
                 onAuth: Callable[[ClientHandler, Any], bool],
                 onMessage: Callable[[ClientHandler, Any], None],
                 onDisconnected: Callable[[ClientHandler], None],) :
        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onAuth,
            onMessage=self._onMessage,
            onDisconnected=self._onDisconnected,
        )

        self.authorized: bool = False
        self.clientId: str = None
        self.clientName: str = None

        self.player: ClientPlayer = None

    def setPlayer(self, player: ClientPlayer) :
        self.player = player

    def forwardMessage(self, message: Any) -> bool :
        if self.player != None :
            return self.player.forwardMessage(message)
        return False

    def _onAuth(self, message) :
        if self.onAuth(self, message) :
            self.authorized = True
            self.clientId = message.clientId
            self.clientName = message.name
            return True
        else :
            return False

    def _onMessage(self, message) :
        self.onMessage(self, message)

    def _onDisconnected(self) :
        self.onDisconnected(self)
