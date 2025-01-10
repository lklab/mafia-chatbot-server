from typing import Callable, Any
import jwt
from datetime import datetime, timezone
import asyncio

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse, ErrorCode

import mafia_chatbot.firebase.firebase as firebase
from mafia_chatbot.db.test_account_db import testAccountDB

from mafia_chatbot.utils.wands_logger import WandsLogger

class ClientHandler :
    pass

class ClientHandler :
    def __init__(self,
                 tcpHandler: TcpHandler,
                 onAuth: Callable[[ClientHandler, str, Any], tuple[Any, ClientUser]],
                 onMessage: Callable[[ClientHandler, Any], None],
                 onDisconnected: Callable[[ClientHandler], None],
                 logger: WandsLogger,
        ) :
        self.addr = tcpHandler.addr

        self.user: ClientUser = None

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected
        self.logger = logger

        self.messageHandler = MessageHandler(
            tcpHandler=tcpHandler,
            onAuth=self._onAuth,
            onMessage=self._onMessage,
            onDisconnected=self._onDisconnected,
        )

    def respond(self, message) :
        if self.user == None :
            return
        self.user.respond(self.messageHandler, message)

    async def _onAuth(self, message) -> tuple[Any, bool] :
        self.logger.debug(f'[ClientHandler] _onAuth() addr={self.addr} message=<{message}>')

        if message.method == auth_pb2.AuthMethod.AUTH_METHOD_TEST :
            response, success = await self._authByTest(message)
        elif message.method == auth_pb2.AuthMethod.AUTH_METHOD_FIREBASE :
            response, success = await self._authByFirebase(message)
        else :
            response = makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'The auth method is invalid.')
            self.logger.error(f'[ClientHandler] auth failed addr={self.addr} response=<{response}>')
            return response, False

        if not success :
            self.logger.error(f'[ClientHandler] auth failed addr={self.addr} response=<{response}>')
            return response, False
        else :
            clientId: str = response

        # auth by upper layer
        response, user = self.onAuth(self, clientId, message)

        # success
        if user != None :
            self.user = user
            user.addConnection(self.messageHandler, message.listen)

            response = auth_pb2.AuthResponse()
            response.rqid = message.rqid
            self.user.toProtoUserInfoMessage(response.userInfo)

            return response, True

        # fail
        else :
            if response == None :
                response = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'Auth failed')
            self.logger.error(f'[ClientHandler] auth failed addr={self.addr} response=<{response}>')
            return response, False

    def _onMessage(self, message) :
        if self.user != None :
            self.onMessage(self, message)

    def _onDisconnected(self) :
        if self.user != None :
            self.user.removeConnection(self.messageHandler)
            self.onDisconnected(self)

    async def _authByTest(self, message) -> tuple[Any, bool] :
        dbData = testAccountDB.get_user_by_id(message.token)
        if dbData == None :
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The account cannot be found.')
            return errorResponse, False

        if dbData[0] != message.password.lower() :
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The password does not match.')
            return errorResponse, False

        return dbData[1], True

    async def _authByFirebase(self, message) -> tuple[Any, bool] :
        # 토큰 발행 시간 확인
        # 다음과 같은 오류로 발행 시간이 시스템 시간보다 미래이면 해당 시간동안 대기 후 검증
        # verifyIdToken error [<class 'firebase_admin._auth_utils.InvalidIdTokenError'>] Token used too early, 1736148080 < 1736148081. Check that your computer's clock is set correctly.
        decodedToken = jwt.decode(message.token, options={"verify_signature": False})
        issueTime = decodedToken.get('iat')
        currentTime = int(datetime.now(timezone.utc).timestamp())
        waitTime = issueTime - currentTime
        if issueTime and waitTime > 0 and waitTime < 60 :
            self.logger.debug(f'[ClientHandler] _onAuth() addr={self.addr}: wait for {waitTime} seconds')
            await asyncio.sleep(waitTime)

        # check ID token
        try :
            clientId = firebase.verifyIdToken(message.token)
        except Exception as e :
            self.logger.error(f'[ClientHandler] _onAuth() addr={self.addr}: verifyIdToken error [{type(e)}] {e}. token={message.token}')
            errorResponse = makeErrorResponse(message, ErrorCode.INVALID_DATA, 'Invalid ID token.')
            return errorResponse, False

        return clientId, True
