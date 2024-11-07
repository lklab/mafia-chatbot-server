import asyncio
from collections import deque
from typing import Callable, Deque

delimiter = b'\xCA\xFE\xBA\xBE'

class TcpClientHandler :
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        self.reader = reader
        self.writer = writer

        self.sendQueue: Deque[bytes] = deque()
        self.isSending = False

        self.addr = self.writer.get_extra_info('peername')
        print(f"Client connected: {self.addr}")

    async def listen(self, onMessage: Callable[[int, bytes], None], onDisconnected: Callable[[], None]) :
        buffer = b''

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
                    onMessage(msg_type, payload)

        except Exception as e:
            print(f"Error: {e}")

        print("Closing connection")
        self.writer.close()
        await self.writer.wait_closed()
        onDisconnected()

    def sendStr(self, type: int, payload: str) :
        self.send(type, payload.encode())

    def send(self, type: int, payload: bytes) :
        data = (
            delimiter +
            type.to_bytes(4, byteorder='big') +
            len(payload).to_bytes(4, byteorder='big') +
            payload
        )
        self.sendQueue.append(data)

        if not self.isSending :
            self.isSending = True
            asyncio.create_task(self._send())

    async def _send(self) :
        while len(self.sendQueue) > 0 :
            data = self.sendQueue.popleft()
            self.writer.write(data)
            await self.writer.drain()
        self.isSending = False
