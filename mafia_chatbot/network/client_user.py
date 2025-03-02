from typing import Callable, Awaitable, Any
import asyncio
import uuid

from mafia_chatbot.game.game_logger import GameLogger, TAG

from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse, ErrorCode

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.user_db import userDB
import mafia_chatbot.utils.name_bank as NameBank

class ClientUser :
    pass

class UserHolder :
    def onUserReleased(self, user: ClientUser) :
        pass

class ClientUser :
    def __init__(self, clientId: str, onRelease: Callable[[ClientUser], None]) :
        self.clientId = clientId
        self.onRelease = onRelease

        # get client name
        dbData = userDB.get_user_by_uid(clientId)
        if dbData != None :
            self.clientName = dbData[1]
        else :
            self.clientName = ''

        # variables
        self.connections: set[MessageHandler] = set()
        self.listenConnection: MessageHandler = None
        self.holders: dict[str, UserHolder] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.logger: GameLogger = None
        self.subscribers: dict[type, Callable[[MessageHandler, uuid.UUID, Any], None]] = {}
        self.isReleased: bool = False
        self.authMethod: auth_pb2.AuthMethod = auth_pb2.AuthMethod.AUTH_METHOD_UNKNOWN

    ### holder ###
    def setHolder(self, key: str, holder: UserHolder) :
        self.holders[key] = holder

    def getHolder(self, key: str) -> UserHolder :
        return self.holders.get(key)

    def releaseHolder(self, key) :
        if key in self.holders :
            del self.holders[key]
            self._checkReleasable()

    def _checkReleasable(self) :
        if len(self.holders) == 0 and len(self.connections) == 0 and not self.isReleased :
            self.isReleased = True
            self.onRelease(self)

    ### task ###
    def createTask(self, key: str, task: Callable, *args, **kwargs) -> bool :
        """동일한 key에 대해 동시에 하나의 태스크만 실행될 수 있도록 보장"""
        if key in self.tasks :
            return False

        self.tasks[key] = asyncio.create_task(self._runTask(key, task, *args, **kwargs))
        return True

    async def _runTask(self, key: str, task: Callable, *args, **kwargs) :
        try :
            await task(*args, **kwargs)
        except :
            raise
        finally :
            del self.tasks[key]

    ### connection ###
    def isConnected(self) :
        return len(self.connections) > 0

    def addConnection(self, connection: MessageHandler, isListen: bool) :
        if self.isReleased :
            return

        self.connections.add(connection)

        if isListen :
            listenConnection = self.listenConnection
            self.listenConnection = connection

            if listenConnection != None :
                message = auth_pb2.DuplicatedSignIn()
                listenConnection.send(message)
                listenConnection.disconnect()

    def removeConnection(self, connection: MessageHandler) :
        if connection in self.connections :
            self.connections.discard(connection)
            if self.listenConnection == connection :
                self.listenConnection = None
            self._checkReleasable()

    def forward(self, connection: MessageHandler, rqid: uuid.UUID, message) :
        # connection이 본 User와 관련된 것임을 assert
        msgType = type(message)
        if msgType in self.subscribers :
            self.subscribers[msgType](connection, rqid, message)
            return True
        else :
            return False

    def respond(self, connection: MessageHandler, rqid: uuid.UUID, message) :
        # connection이 본 User와 관련된 것임을 assert
        if self.logger != None :
            self.logger.log(TAG.NETWORK, f'[ClientUser] respond {type(message)} message to {self.clientName}: <{message}>')
        connection.send(message, rqid)

    def send(self, message) :
        if self.listenConnection != None :
            if self.logger != None :
                self.logger.log(TAG.NETWORK, f'[ClientUser] send {type(message)} message to {self.clientName}: <{message}>')
            self.listenConnection.send(message)

    def setLogger(self, logger: GameLogger) :
        self.logger = logger

    def subscribeMessage(self, msgType: type, listener: Callable[[MessageHandler, uuid.UUID, Any], None]) :
        self.subscribers[msgType] = listener

    def clearSubscribers(self) :
        self.subscribers.clear()
        self.logger = None

    def disconnect(self) :
        # disconnect 과정에서 self.removeConnection() 함수가 호출될 수 있으므로 복사
        connections: set[MessageHandler] = self.connections.copy()
        self.connections.clear()
        self.listenConnection = None

        for connection in connections :
            connection.disconnect()

        self._checkReleasable()

    ### user info ###
    def setAuthMethod(self, method: auth_pb2.AuthMethod) :
        self.authMethod = method

    def toProtoUserInfoMessage(self, message_out: auth_pb2.UserInfo) :
        message_out.clientId = self.clientId
        message_out.name = self.clientName

    async def updateInfo(self, message: auth_pb2.UpdateUserInfo) -> Any :
        # check name
        name = message.userInfo.name.strip()
        result = await NameBank.checkName(name)

        # success
        if result == NameBank.Result.SUCCESS :
            try :
                userDB.upsert_user(self.clientId, name)
            except :
                errorResponse = makeErrorResponse(message, ErrorCode.SERVER_ERROR, 'DB error occurred. try again.')
                return errorResponse

            self.clientName = name

            response = auth_pb2.UpdateUserInfoResponse()
            self.toProtoUserInfoMessage(response.userInfo)
            return response

        # fail
        else :
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'This name is not suitable for use in a Mafia game.')
            return errorResponse

    def isNeedToSignUp(self) -> bool :
        return len(self.clientName) == 0

    def delete(self) :
        holders = list(self.holders.values())
        self.holders.clear()

        for holder in holders :
            holder.onUserReleased(self)

        if self.authMethod == auth_pb2.AuthMethod.AUTH_METHOD_FIREBASE :
            firebase.deleteUser(self.clientId) # TODO 삭제된 사용자 uid 일정 기간동안 보유하면서 새로운 연결 막기
            userDB.delete_user_by_uid(self.clientId)
