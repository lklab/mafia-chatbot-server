import asyncio
from typing import Callable
from enum import Enum
import traceback

class TcpState(Enum) :
    INITIALIZED = 0
    CONNECTED = 1
    DISCONNECTED = 2

delimiter = b'\xCA\xFE\xBA\xBE'
maxPayloadSize = 10 * 1024 * 1024 # 10Mb

MAX_FAIL_COUNT = 5

class TcpHandler :
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, trust: bool = False) :
        self.state = TcpState.INITIALIZED

        self.reader = reader
        self.writer = writer
        self.trust = trust
        self.listenTask: asyncio.Task = None

        self.addr = self.writer.get_extra_info('peername')
        self.ip: str = self.writer.get_extra_info('peername')[0]
        self.port: int = self.writer.get_extra_info('peername')[1]

        self.failCount: int = 0

    def listen(self, onData: Callable[[int, bytes], None], onDisconnected: Callable[[], None]) :
        if self.state != TcpState.INITIALIZED :
            return
        self.state = TcpState.CONNECTED

        self.listenTask = asyncio.create_task(self._listen(onData, onDisconnected))

    async def _listen(self, onData: Callable[[int, bytes], None], onDisconnected: Callable[[], None]) :
        buffer = b''
        self.onDisconnected = onDisconnected

        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk or self.state == TcpState.DISCONNECTED :
                    break
                buffer += chunk

                # print(f'[TcpHandler] {self.addr} buffer: ' + ' '.join(f'0x{byte:02x}' for byte in buffer))

                while True :
                    # check delimiter
                    cursor = buffer.find(delimiter)
                    if cursor == -1 :
                        buffer = b''
                        self.addFailCount()
                        break
                    cursor += 4

                    # get message type and payload size
                    if len(buffer) < cursor + 8 :
                        break
                    msg_type = int.from_bytes(buffer[cursor:cursor+4], byteorder='big')
                    cursor += 4
                    payload_size = int.from_bytes(buffer[cursor:cursor+4], byteorder='big')
                    cursor += 4

                    # check payload size
                    if payload_size > maxPayloadSize :
                        buffer = buffer[cursor:]
                        self.addFailCount()
                        continue

                    # get payload
                    if len(buffer) < cursor + payload_size :
                        break
                    payload = buffer[cursor:cursor+payload_size]
                    cursor += payload_size

                    # remove one message
                    buffer = buffer[cursor:]

                    try :
                        # forward payload
                        onData(msg_type, payload)
                    except Exception as e:
                        print(f"[TcpHandler] {self.addr} onData error: {e}")
                        traceback.print_exc()
        except asyncio.CancelledError:
            print("[TcpHandler] listen task is cancelled.")
        except Exception as e:
            print(f"[TcpHandler] {self.addr} comm error: {e}")

        print(f"[TcpHandler] {self.addr} Closing connection")
        self.listenTask = None
        await self.close()

    async def sendStr(self, type: int, payload: str) -> bool :
        return await self.send(type, payload.encode())

    async def send(self, type: int, payload: bytes) -> bool :
        if self.state != TcpState.CONNECTED :
            return False

        data = (
            delimiter +
            type.to_bytes(4, byteorder='big') +
            len(payload).to_bytes(4, byteorder='big') +
            payload
        )

        try:
            self.writer.write(data)
            await self.writer.drain()

        except (OSError, asyncio.CancelledError, BrokenPipeError, ConnectionResetError) as e:
            print(f"[TcpHandler] {self.addr} fail to send data: {e}")
            await self.close()
            return False

        return True

    def addFailCount(self) :
        if self.trust :
            return

        self.failCount += 1
        if self.failCount >= MAX_FAIL_COUNT :
            asyncio.create_task(self.close())

    def resetFailCount(self) :
        self.failCount = 0

    async def close(self) :
        if self.state == TcpState.DISCONNECTED :
            return
        self.state = TcpState.DISCONNECTED

        # cancel listen task
        if self.listenTask != None :
            task = self.listenTask
            self.listenTask = None

        try :
            task.cancel()
            await task
        except :
            pass

        # close writer
        try :
            self.writer.close()
            await self.writer.wait_closed()
        except :
            pass

        try :
            self.onDisconnected()
        except :
            pass
