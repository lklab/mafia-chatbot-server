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

class TcpHandler :
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        self.state = TcpState.INITIALIZED

        self.reader = reader
        self.writer = writer

        self.addr = self.writer.get_extra_info('peername')

    def listen(self, onData: Callable[[int, bytes], None], onDisconnected: Callable[[], None]) :
        asyncio.create_task(self._listen(onData, onDisconnected))

    async def _listen(self, onData: Callable[[int, bytes], None], onDisconnected: Callable[[], None]) :
        if self.state != TcpState.INITIALIZED :
            return
        self.state = TcpState.CONNECTED

        buffer = b''
        self.onDisconnected = onDisconnected

        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                buffer += chunk

                # print(f'[TcpHandler] {self.addr} buffer: ' + ' '.join(f'0x{byte:02x}' for byte in buffer))

                while True :
                    # check delimiter
                    cursor = buffer.find(delimiter)
                    if cursor == -1 :
                        buffer = b''
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

        except Exception as e:
            print(f"[TcpHandler] {self.addr} comm error: {e}")

        print(f"[TcpHandler] {self.addr} Closing connection")
        await self._close()

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
            return True

        except (OSError, asyncio.CancelledError) as e:
            print(f"[TcpHandler] {self.addr} fail to send data: {e}")
            await self._close()

        return False

    async def _close(self) :
        if self.state == TcpState.DISCONNECTED :
            return
        self.state = TcpState.DISCONNECTED

        try :
            self.writer.close()
            await self.writer.wait_closed()
        except Exception as e :
            print(f"[TcpHandler] {self.addr} fail to close: {e}")

        self.onDisconnected()
