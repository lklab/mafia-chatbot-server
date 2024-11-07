import asyncio
from typing import Callable

delimiter = b'\xCA\xFE\xBA\xBE'

class TcpClientHandler :
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        self.reader = reader
        self.writer = writer

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

    async def sendStr(self, type: int, data: bytes) :
        self.writer.write(delimiter +
            type.to_bytes(4, byteorder='big') +
            len(data).to_bytes(4, byteorder='big') +
            data
        )
        await self.writer.drain()
