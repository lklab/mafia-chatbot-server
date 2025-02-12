import asyncio
from enum import Enum
from collections import deque
from typing import Callable, Awaitable, Deque, Any
import uuid
from datetime import datetime, timedelta

from mafia_chatbot.network.tcp_handler import TcpHandler
from mafia_chatbot.network.messages.message_info import messageTypeDict, messageFactoryDict
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse, ErrorCode

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
        self.ip = tcpHandler.ip
        self.port = tcpHandler.port
        self.desc: str = ''

        self.onAuth = onAuth
        self.onMessage = onMessage
        self.onDisconnected = onDisconnected

        self.authTask: asyncio.Task = None

        self.sendTask: asyncio.Task = None
        self.sendQueue: Deque[tuple[int, bytes]] = deque()
        self.responseAwaiters: dict[str, asyncio.Future] = {}

        self._security_authTimeoutTask: asyncio.Task = None
        self._security_noCommCheckTask: asyncio.Task = None
        self._security_lastCommTime: datetime = datetime.now()
        self._security_commCount: int = 0
        self._security_resetCommLimitTask: asyncio.Task = None

        if not tcpHandler.trust :
            if onAuth != None :
                self._security_startAuthTimeout()
            self._security_startNoCommCheckTask()
            self._security_startResetCommLimitTask()

        self.tcpHandler.listen(
            onData=self._onData,
            onDisconnected=self._onDisconnected,
        )

    def send(self, message) :
        if self.state != MessageState.CONNECTED :
            return
        self._send(message)

    async def sendAwaitResponse(self, message, timeout: float = 10) :
        if self.state != MessageState.CONNECTED :
            return

        rqid = str(uuid.uuid4())
        message.rqid = rqid

        future = asyncio.Future()
        self.responseAwaiters[rqid] = future

        self._send(message)

        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as e :
            print(f'[MessageHandler] {self.tcpHandler.addr} No response for request {rqid} within timeout: {e}\nmessage=<{message}>')
            raise TimeoutError(f"No response for request {rqid} within timeout: {e}\nmessage=<{message}>")
        finally :
            del self.responseAwaiters[rqid]

    def setDesc(self, desc: str) :
        self.desc = desc

    def disconnect(self) :
        if self.state == MessageState.DISCONNECTED :
            return
        self.state = MessageState.DISCONNECTED

        self._security_stopAuthTimeout()
        self._security_stopNoCommCheckTask()
        self._security_stopResetCommLimitTask()

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

        if not self.tcpHandler.trust :
            self._security_lastCommTime = datetime.now()

            if self._security_commCount >= 300 :
                self.disconnect()
                return
            self._security_commCount += 1

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
                    if success :
                        self._security_stopAuthTimeout()
                        self.state = MessageState.CONNECTED
                    self.authTask = None
                    self._send(response)

                if self.authTask != None :
                    errorResponse = makeErrorResponse(message, ErrorCode.BUSY, 'It is already being processed.')
                    self._send(errorResponse)
                    return

                self.authTask = asyncio.create_task(_auth())
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
        # print(f'[MessageHandler] {self.tcpHandler.addr} onDisconnected')
        self.onDisconnected()

    async def _sendQueuedMessages(self) :
        while len(self.sendQueue) > 0 :
            msgType, data = self.sendQueue[0]
            # 연결이 해제된 경우 tcpHandler.send()에서 False를 반환하므로 따로 검사하지 않아도 괜찮음
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

    def _security_startAuthTimeout(self) :
        async def _task() :
            await asyncio.sleep(60)
            self.disconnect()

        self._security_authTimeoutTask = asyncio.create_task(_task())

    def _security_stopAuthTimeout(self) :
        async def _task() :
            if self._security_authTimeoutTask != None :
                task = self._security_authTimeoutTask
                self._security_authTimeoutTask = None

                task.cancel()
                try :
                    await task
                except :
                    pass

        asyncio.create_task(_task())

    def _security_startNoCommCheckTask(self) :
        async def _task() :
            while True :
                await asyncio.sleep(3600)
                diff: timedelta = datetime.now() - self._security_lastCommTime
                if diff > timedelta(hours=1) :
                    self.disconnect()
                    return

        self._security_noCommCheckTask = asyncio.create_task(_task())

    def _security_stopNoCommCheckTask(self) :
        async def _task() :
            if self._security_noCommCheckTask != None :
                task = self._security_noCommCheckTask
                self._security_noCommCheckTask = None

                task.cancel()
                try :
                    await task
                except :
                    pass

        asyncio.create_task(_task())

    def _security_startResetCommLimitTask(self) :
        async def _task() :
            while True :
                await asyncio.sleep(60)
                self._security_commCount = 0

        self._security_resetCommLimitTask = asyncio.create_task(_task())

    def _security_stopResetCommLimitTask(self) :
        async def _task() :
            if self._security_resetCommLimitTask != None :
                task = self._security_resetCommLimitTask
                self._security_resetCommLimitTask = None

                task.cancel()
                try :
                    await task
                except :
                    pass

        asyncio.create_task(_task())
