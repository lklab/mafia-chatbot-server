import asyncio
from enum import Enum
from collections import deque
from typing import Callable, Deque, Type, Any

from mafia_chatbot.network.tcp_client_handler import TcpClientHandler
from mafia_chatbot.network.data import *

messageTypeDict: dict[Type, int] = {
    auth_pb2.Auth : 0,
    auth_pb2.AuthResponse : 1,
}

def AuthMessageFactory(data: bytes) -> auth_pb2.Auth :
    message = auth_pb2.Auth()
    message.ParseFromString(data)
    return message

def AuthResponseMessageFactory(data: bytes) -> auth_pb2.AuthResponse :
    message = auth_pb2.AuthResponse()
    message.ParseFromString(data)
    return message

messageFactoryDict: dict[int, Callable[[bytes], Any]] = {
    0 : AuthMessageFactory,
    1 : AuthResponseMessageFactory,
}

class MessageClientState(Enum) :
    AUTHENTICATING = 0
    CONNECTED = 1
    DISCONNECTED = 2

class MessageClientHandler :
    def __init__(
            self,
            tcpHandler: TcpClientHandler,
            onAuth: Callable[[Any], bool],
            onMessage: Callable[[Any], None],
            onDisconnected: Callable[[], None],
        ) :
        self.state = MessageClientState.AUTHENTICATING
        self.tcpHandler = tcpHandler

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.sendQueue: Deque[tuple[int, bytes]] = deque()
        self.isSending = False

        asyncio.create_task(self.tcpHandler.listen(
            onData=self._onData,
            onDisconnected=self._onDisconnected,
        ))

    def send(self, message) :
        if self.state != MessageClientState.CONNECTED :
            return
        self._send(message)

    def _send(self, message) :
        if type(message) in messageTypeDict :
            msgType = messageTypeDict[type(message)]
            data = message.SerializeToString()
            self.sendQueue.append((msgType, data))
            asyncio.create_task(self._sendQueuedMessages())

    def _onData(self, msgType: int, data: bytes) :
        if self.state == MessageClientState.AUTHENTICATING :
            if msgType == 0 :
                message = messageFactoryDict[0](data)
                print(f'onData msgType={msgType}, message=<{message}>')

                if self.onAuth(message) :
                    authResponse = auth_pb2.AuthResponse()
                    authResponse.rqid = message.rqid
                    self._send(authResponse)
                    self.state = MessageClientState.CONNECTED
        else :
            if msgType in messageFactoryDict :
                message = messageFactoryDict[msgType](data)
                print(f'onData msgType={msgType}, message=<{message}>')
                self.onMessage(message)

    def _onDisconnected(self) :
        self.state = MessageClientState.DISCONNECTED
        print('onDisconnected')
        self.onDisconnected()

    async def _sendQueuedMessages(self) :
        if self.isSending :
            return
        self.isSending = True

        while len(self.sendQueue) > 0 and self.state != MessageClientState.DISCONNECTED :
            msgType, data = self.sendQueue[0]
            success = await self.tcpHandler.send(msgType, data)
            if success :
                self.sendQueue.popleft()
            else :
                break

        self.isSending = False
