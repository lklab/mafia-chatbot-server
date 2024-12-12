import asyncio
import ssl
from typing import Callable

from mafia_chatbot.network.tcp_handler import TcpClientHandler

class TcpServer :
    def __init__(self, port: int, useSSL: bool = True) :
        self.server = None
        self.port: int = port
        self.useSSL: bool = useSSL

    async def start(self, onConnected: Callable[[TcpClientHandler], None]) :
        self.onConnected = onConnected

        if self.useSSL :
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(
                certfile='server.crt',
                keyfile='server.key',
                password='1227',
            )

            self.server = await asyncio.start_server(
                self._handle_client, '0.0.0.0', self.port, ssl=ssl_context
            )
        else :
            self.server = await asyncio.start_server(
                self._handle_client, '0.0.0.0', self.port
            )

        addr = self.server.sockets[0].getsockname()
        print(f'[TcpServer] Server started on {addr}')

    async def serve(self) :
        if self.server :
            try :
                await self.server.serve_forever()
            except asyncio.CancelledError :
                print("[TcpServer] Server cancelled")
        else:
            print("[TcpServer] Server has not been started yet. Please call start() first.")

    async def close(self) :
        if self.server:
            print("[TcpServer] Shutting down server...")
            self.server.close()
            await self.server.wait_closed()
            print("[TcpServer] Server shut down complete.")
        else:
            print("[TcpServer] Server is not running.")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        clientHandler = TcpClientHandler(reader, writer)
        print(f"[TcpServer] {clientHandler.addr} Client connected")
        self.onConnected(clientHandler)
