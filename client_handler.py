from typing import Callable, Any

from mafia_chatbot.game.client_player import ClientPlayer

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.user_db import userDB

import mafia_chatbot.utils.name_bank as name_bank

class ClientHandler :
    pass

class ClientHandler :
    def __init__(self,
                 tcpHandler: TcpHandler,
                 onAuth: Callable[[ClientHandler, str, Any], tuple[Any, bool]],
                 onMessage: Callable[[ClientHandler, Any], None],
                 onDisconnected: Callable[[ClientHandler], None],) :
        self.addr = tcpHandler.addr

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
        self.clientName: str = ''

        self.player: ClientPlayer = None

    def setPlayer(self, player: ClientPlayer) :
        self.player = player

    def forwardMessage(self, message: Any) -> bool :
        if self.player != None :
            return self.player.forwardMessage(message)
        return False

    def toProtoUserInfoMessage(self, message_out: auth_pb2.UserInfo) :
        message_out.clientId = self.clientId
        message_out.name = self.clientName

    def isReady(self) -> bool :
        return isinstance(self.clientName, str) and len(self.clientName) > 0

    def deleteUser(self) :
        firebase.deleteUser(self.clientId)
        userDB.delete_user_by_uid(self.clientId)

    async def updateInfo(self, message: auth_pb2.UpdateUserInfo) -> Any :
        name = message.userInfo.name.strip()

        result = await name_bank.checkName(name)

        if result == name_bank.Result.SUCCESS :
            try :
                userDB.upsert_user(self.clientId, name)
            except :
                errorResponse = makeErrorResponse(message, 0, 'DB error occurred. try again.')
                return errorResponse

            self.clientName = name

            response = auth_pb2.UpdateUserInfoResponse()
            response.rqid = message.rqid
            self.toProtoUserInfoMessage(response.userInfo)
            return response

        else :
            errorResponse = makeErrorResponse(message, 0, 'This name is not suitable for use in a Mafia game.')
            return errorResponse

    def disconnect(self) :
        self.messageHandler.disconnect()

    def _onAuth(self, message) -> tuple[Any, bool] :
        clientId = firebase.verifyIdToken(message.token)
        if clientId == None :
            errorResponse = makeErrorResponse(message, 0, 'Invalid ID token.')
            return errorResponse, False

        response, success = self.onAuth(self, clientId, message)

        if success :
            self.authorized = True
            self.clientId = clientId

            dbData = userDB.get_user_by_uid(clientId)
            if dbData != None :
                self.clientName = dbData[1]

            response = auth_pb2.AuthResponse()
            response.rqid = message.rqid
            self.toProtoUserInfoMessage(response.userInfo)

        else :
            if response == None :
                response = makeErrorResponse(message, 0, 'Auth failed')

        return response, success

    def _onMessage(self, message) :
        self.onMessage(self, message)

    def _onDisconnected(self) :
        self.onDisconnected(self)
