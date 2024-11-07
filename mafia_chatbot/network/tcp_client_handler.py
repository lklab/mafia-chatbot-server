import asyncio
from typing import Callable
from enum import Enum

class TcpClientState(Enum) :
    INITIALIZED = 0
    CONNECTED = 1
    DISCONNECTED = 2

delimiter = b'\xCA\xFE\xBA\xBE'

class TcpClientHandler :
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        self.state = TcpClientState.INITIALIZED

        self.reader = reader
        self.writer = writer

        self.addr = self.writer.get_extra_info('peername')
        print(f"Client connected: {self.addr}")

    async def listen(self, onData: Callable[[int, bytes], None], onDisconnected: Callable[[], None]) :
        if self.state != TcpClientState.INITIALIZED :
            return
        self.state = TcpClientState.CONNECTED

        buffer = b''
        self.onDisconnected = onDisconnected

        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                buffer += chunk

                # print('buffer: ' + ' '.join(f'0x{byte:02x}' for byte in buffer))

                while True :
                    # check delimiter
                    cursor = buffer.find(delimiter)
                    if cursor == -1 :
                        break
                    cursor += 4

                    # get message type and payload size
                    if len(buffer) < cursor + 8 :
                        break
                    msg_type = int.from_bytes(buffer[cursor:cursor+4], byteorder='big')
                    cursor += 4
                    payload_size = int.from_bytes(buffer[cursor:cursor+4], byteorder='big')
                    cursor += 4

                    # get payload
                    if len(buffer) > cursor + payload_size :
                        break
                    payload = buffer[cursor:cursor+payload_size]
                    cursor += payload_size

                    # remove one message
                    buffer = buffer[cursor:]

                    # forward payload
                    onData(msg_type, payload)

        except Exception as e:
            print(f"Error: {e}")

        print("Closing connection")
        await self._close()

    async def sendStr(self, type: int, payload: str) -> bool :
        return await self.send(type, payload.encode())

    async def send(self, type: int, payload: bytes) -> bool :
        if self.state != TcpClientState.CONNECTED :
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
            print(f"fail to send data: {e}")
            await self._close()

        return False

    async def _close(self) :
        if self.state == TcpClientState.DISCONNECTED :
            return

        self.state = TcpClientState.DISCONNECTED
        self.writer.close()
        await self.writer.wait_closed()
        self.onDisconnected()
