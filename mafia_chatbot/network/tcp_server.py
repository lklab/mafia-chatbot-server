import asyncio
import ssl
from typing import Callable

from mafia_chatbot.network.tcp_client_handler import TcpClientHandler

class TcpServer :
    def __init__(self) :
        self.server = None

    async def start(self, onConnected: Callable[[TcpClientHandler], None]) :
        self.onConnected = onConnected

        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile='server.crt', keyfile='server.key')

        self.server = await asyncio.start_server(
            self._handle_client, '0.0.0.0', 10015, ssl=ssl_context
        )

        addr = self.server.sockets[0].getsockname()
        print(f'Server started on {addr}')

    async def serve(self) :
        if self.server :
            await self.server.serve_forever()
        else:
            print("Server has not been started yet. Please call start() first.")

    async def close(self) :
        if self.server:
            print("Shutting down server...")
            self.server.close()
            await self.server.wait_closed()
            print("Server shut down complete.")
        else:
            print("Server is not running.")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        clientHandler = TcpClientHandler(reader, writer)
        self.onConnected(clientHandler)
