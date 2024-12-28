from typing import Callable, Any

from mafia_chatbot.game.client_player import ClientPlayer

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.user_db import userDB

import mafia_chatbot.utils.name_bank as name_bank

class ClientHandler :
    pass

class ClientHandler :
    def __init__(self,
                 tcpHandler: TcpHandler,
                 onAuth: Callable[[ClientHandler, str], tuple[Any, bool]],
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

    async def updateInfo(self, message: auth_pb2.UpdateUserInfo) -> Any :
        name = message.userInfo.name.strip()

        result = await name_bank.checkName(name)

        if result == name_bank.Result.SUCCESS :
            self.clientName = name
            userDB.upsert_user(self.clientId, name)

            response = auth_pb2.UpdateUserInfoResponse()
            response.rqid = message.rqid
            self.toProtoUserInfoMessage(response.userInfo)
            return response

        else :
            errorResponse = error_pb2.RequestError()
            errorResponse.rqid = message.rqid
            errorResponse.rqtype = messageTypeDict[type(message)]
            errorResponse.code = 0
            errorResponse.detail = 'This name is not suitable for use in a Mafia game.'
            return errorResponse

    def _onAuth(self, message) -> tuple[Any, bool] :
        clientId = firebase.verifyIdToken(message.token)
        if clientId == None :
            errorResponse = error_pb2.RequestError()
            errorResponse.rqid = message.rqid
            errorResponse.rqtype = messageTypeDict[type(message)]
            errorResponse.code = 0
            errorResponse.detail = 'Invalid ID token.'
            return errorResponse, False

        response, success = self.onAuth(self, clientId)

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
                response = error_pb2.RequestError()
                response.code = 0
                response.detail = 'Auth failed'

            response.rqid = message.rqid
            response.rqtype = messageTypeDict[type(message)]

        return response, success

    def _onMessage(self, message) :
        self.onMessage(self, message)

    def _onDisconnected(self) :
        self.onDisconnected(self)
