from typing import Callable, Any

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse

import mafia_chatbot.firebase.firebase as firebase

class ClientHandler :
    pass

class ClientHandler :
    def __init__(self,
                 tcpHandler: TcpHandler,
                 onAuth: Callable[[ClientHandler, str, Any], tuple[Any, ClientUser]],
                 onMessage: Callable[[ClientUser, Any], None],
                 onDisconnected: Callable[[ClientUser], None],
        ) :
        self.addr = tcpHandler.addr

        self.user: ClientUser = None

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onAuth,
            onMessage=self._onMessage,
            onDisconnected=self._onDisconnected,
        )

    def _onAuth(self, message) -> tuple[Any, bool] :
        # check ID token
        clientId = firebase.verifyIdToken(message.token)
        if clientId == None :
            errorResponse = makeErrorResponse(message, 0, 'Invalid ID token.')
            return errorResponse, False

        # auth by upper layer
        response, user = self.onAuth(self, clientId, message)

        # success
        if user != None :
            self.user = user
            user.setMessageHandler(self.messageHandler)

            response = auth_pb2.AuthResponse()
            response.rqid = message.rqid
            self.user.toProtoUserInfoMessage(response.userInfo)

            return response, True

        # fail
        else :
            if response == None :
                response = makeErrorResponse(message, 0, 'Auth failed')
            return response, False

    def _onMessage(self, message) :
        if self.user != None :
            self.onMessage(self.user, message)

    def _onDisconnected(self) :
        if self.user != None :
            self.user.clearMessageHandler()
            self.onDisconnected(self.user)
