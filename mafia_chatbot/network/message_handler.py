import asyncio
from enum import Enum
from collections import deque
from typing import Callable, Deque, Any

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.messages.message_info import *
from mafia_chatbot.network.messages import *

class MessageState(Enum) :
    AUTHENTICATING = 0
    CONNECTED = 1
    DISCONNECTED = 2

class MessageHandler :
    def __init__(
            self,
            tcpHandler: TcpHandler,
            onAuth: Callable[[Any], bool],
            onMessage: Callable[[Any], None],
            onDisconnected: Callable[[], None],
        ) :
        if onAuth != None :
            self.state = MessageState.AUTHENTICATING
        else :
            self.state = MessageState.CONNECTED
        self.tcpHandler = tcpHandler

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.sendQueue: Deque[tuple[int, bytes]] = deque()
        self.isSending = False

        self.tcpHandler.listen(
            onData=self._onData,
            onDisconnected=self._onDisconnected,
        )

    def send(self, message) :
        if self.state != MessageState.CONNECTED :
            return
        self._send(message)

    def _send(self, message) :
        if type(message) in messageTypeDict :
            msgType = messageTypeDict[type(message)]
            data = message.SerializeToString()
            self.sendQueue.append((msgType, data))
            asyncio.create_task(self._sendQueuedMessages())

    def _onData(self, msgType: int, data: bytes) :
        if self.state == MessageState.AUTHENTICATING :
            if msgType == messageTypeDict[auth_pb2.Auth] :
                message = messageFactoryDict[msgType](data)
                # print(f'[MessageHandler] {self.tcpHandler.addr} onData msgType={msgType}, message=<{message}>')

                if self.onAuth(message) :
                    authResponse = auth_pb2.AuthResponse()
                    authResponse.rqid = message.rqid
                    self._send(authResponse)
                    self.state = MessageState.CONNECTED
        else :
            if msgType in messageFactoryDict :
                message = messageFactoryDict[msgType](data)
                # print(f'[MessageHandler] {self.tcpHandler.addr} onData msgType={msgType}, message=<{message}>')
                self.onMessage(message)

    def _onDisconnected(self) :
        self.state = MessageState.DISCONNECTED
        print(f'[MessageHandler] {self.tcpHandler.addr} onDisconnected')
        self.onDisconnected()

    async def _sendQueuedMessages(self) :
        if self.isSending :
            return
        self.isSending = True

        while len(self.sendQueue) > 0 and self.state != MessageState.DISCONNECTED :
            msgType, data = self.sendQueue[0]
            success = await self.tcpHandler.send(msgType, data)
            if success :
                self.sendQueue.popleft()
            else :
                break

        self.isSending = False
