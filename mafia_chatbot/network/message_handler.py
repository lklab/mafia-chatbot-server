import asyncio
from enum import Enum
from collections import deque
from typing import Callable, Awaitable, Deque, Any
import uuid

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
            onAuth: Callable[[Any], Awaitable[tuple[Any, bool]]],
            onMessage: Callable[[Any], None],
            onDisconnected: Callable[[], None],
        ) :
        if onAuth != None :
            self.state = MessageState.AUTHENTICATING
        else :
            self.state = MessageState.CONNECTED
        self.tcpHandler = tcpHandler
        self.addr = tcpHandler.addr
        self.desc: str = ''

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.sendTask: asyncio.Task = None
        self.sendQueue: Deque[tuple[int, bytes]] = deque()
        self.responseAwaiters: dict[str, asyncio.Future] = {}

        self.tcpHandler.listen(
            onData=self._onData,
            onDisconnected=self._onDisconnected,
        )

    def send(self, message) :
        if self.state != MessageState.CONNECTED :
            return
        self._send(message)

    async def sendAwaitResponse(self, message) :
        if self.state != MessageState.CONNECTED :
            return

        rqid = str(uuid.uuid4())
        message.rqid = rqid

        future = asyncio.Future()
        self.responseAwaiters[rqid] = future

        self._send(message)

        try:
            return await asyncio.wait_for(future, 10)
        except asyncio.TimeoutError as e :
            del self.responseAwaiters[rqid]
            print(f'[MessageHandler] {self.tcpHandler.addr} No response for request {rqid} within timeout: {e}\nmessage=<{message}>')
            raise TimeoutError(f"No response for request {rqid} within timeout: {e}\nmessage=<{message}>")

    def setDesc(self, desc: str) :
        self.desc = desc

    def disconnect(self) :
        if self.state == MessageState.DISCONNECTED :
            return
        self.state = MessageState.DISCONNECTED

        asyncio.create_task(self._disconnectTask())

    def _send(self, message) :
        if type(message) in messageTypeDict :
            msgType = messageTypeDict[type(message)]
            data = message.SerializeToString()
            self.sendQueue.append((msgType, data))

            if self.sendTask == None :
                self.sendTask = asyncio.create_task(self._sendQueuedMessages())

    def _onData(self, msgType: int, data: bytes) :
        if self.state == MessageState.DISCONNECTED :
            return

        if self.state == MessageState.AUTHENTICATING :
            if msgType == messageTypeDict[auth_pb2.Auth] :
                try :
                    message = messageFactoryDict[msgType](data)
                except :
                    self.tcpHandler.addFailCount()
                    return
                self.tcpHandler.resetFailCount()
                # print(f'[MessageHandler] {self.tcpHandler.addr} onData msgType={msgType}, message=<{message}>')

                async def _auth() :
                    response, success = await self.onAuth(message)
                    response.rqid = message.rqid
                    self._send(response)
                    if success :
                        self.state = MessageState.CONNECTED

                asyncio.create_task(_auth()) # TODO 중복 호출 처리
            else :
                self.tcpHandler.addFailCount()
                return
        else :
            if msgType in messageFactoryDict :
                try :
                    message = messageFactoryDict[msgType](data)
                except :
                    self.tcpHandler.addFailCount()
                    return
                self.tcpHandler.resetFailCount()
                # print(f'[MessageHandler] {self.tcpHandler.addr} onData msgType={msgType}, message=<{message}>')

                if message.rqid in self.responseAwaiters :
                    future = self.responseAwaiters.pop(message.rqid, None)
                    if future and not future.done() :
                        future.set_result(message)
                else :
                    self.onMessage(message)

    def _onDisconnected(self) :
        self.state = MessageState.DISCONNECTED
        print(f'[MessageHandler] {self.tcpHandler.addr} onDisconnected')
        self.onDisconnected()

    async def _sendQueuedMessages(self) :
        while len(self.sendQueue) > 0 and self.state != MessageState.DISCONNECTED :
            msgType, data = self.sendQueue[0]
            success = await self.tcpHandler.send(msgType, data)
            if success :
                self.sendQueue.popleft()
            else :
                break

        self.sendTask = None

    async def _disconnectTask(self) :
        if self.sendTask != None :
            sendTask: asyncio.Task = self.sendTask
            await sendTask

        await self.tcpHandler.close()
