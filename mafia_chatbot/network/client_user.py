from typing import Callable, Any

from mafia_chatbot.game.game_logger import GameLogger, TAG

from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.user_db import userDB
import mafia_chatbot.utils.name_bank as name_bank

class ClientUser :
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
        self.handler = None
        self.holders: dict[str, object] = {}
        self.logger: GameLogger = None
        self.subscribers: dict[type, Callable[[Any], None]] = {}
        self.isReleased: bool = False

    ### holder ###
    def setHolder(self, key: str, holder: object) :
        self.holders[key] = holder

    def getHolder(self, key: str) -> object :
        return self.holders.get(key)

    def releaseHolder(self, key) :
        if key in self.holders :
            del self.holders[key]
            self._checkReleasable()

    def _checkReleasable(self) :
        if len(self.holders) <= 0 and self.handler == None and not self.isReleased :
            self.isReleased = True
            self.onRelease(self)

    ### message ###
    def setMessageHandler(self, handler: MessageHandler) :
        if self.isReleased :
            return
        self.handler = handler

    def clearMessageHandler(self) :
        self.handler = None
        self._checkReleasable()

    def forward(self, message) :
        if self.handler == None :
            return False

        msgType = type(message)
        if msgType in self.subscribers :
            self.subscribers[msgType](message)
            return True
        else :
            return False

    def send(self, message) :
        if self.handler != None :
            if self.logger != None :
                self.logger.log(TAG.NETWORK, f'[ClientUser] send message to {self.clientName}: <{message}>')
            self.handler.send(message)

    def setLogger(self, logger: GameLogger) :
        self.logger = logger

    def subscribeMessage(self, msgType: type, listener: Callable[[Any], None]) :
        self.subscribers[msgType] = listener

    def clearSubscribers(self) :
        self.subscribers.clear()

    def disconnect(self) :
        if self.handler != None :
            messageHandler: MessageHandler = self.handler
            self.clearMessageHandler()
            messageHandler.disconnect()

    ### user info ###
    def toProtoUserInfoMessage(self, message_out: auth_pb2.UserInfo) :
        message_out.clientId = self.clientId
        message_out.name = self.clientName

    async def updateInfo(self, message: auth_pb2.UpdateUserInfo) -> Any :
        # check name
        name = message.userInfo.name.strip()
        result = await name_bank.checkName(name)

        # success
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

        # fail
        else :
            errorResponse = makeErrorResponse(message, 0, 'This name is not suitable for use in a Mafia game.')
            return errorResponse

    def isNeedToSignUp(self) -> bool :
        return len(self.clientName) == 0

    def delete(self) -> bool :
        if self.refCount > 0 :
            return False

        firebase.deleteUser(self.clientId) # TODO 삭제된 사용자 uid 일정 기간동안 보유하면서 새로운 연결 막기
        userDB.delete_user_by_uid(self.clientId)

        return True
