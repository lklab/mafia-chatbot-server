import asyncio
import ssl
from typing import Callable

from mafia_chatbot.network.tcp_handler import TcpHandler
import mafia_chatbot.utils.server_config as server_config

class TcpServer :
    def __init__(self, port: int, host: str = '0.0.0.0', useSSL: bool = True, trust: bool = False) :
        self.server = None
        self.host: str = host
        self.port: int = port
        self.useSSL: bool = useSSL
        self.trust: bool = trust

    async def start(self, onConnected: Callable[[TcpHandler], None]) :
        self.onConnected = onConnected

        if self.useSSL :
            # openssl req -x509 -nodes -newkey rsa:2048 -keyout server.key -out server.crt -days 365 -subj "/CN=211.47.119.124" -addext "subjectAltName=IP:211.47.119.124"
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(
                certfile=server_config.getCertfile(),
                keyfile=server_config.getKeyfile(),
            )

            self.server = await asyncio.start_server(
                self._handle_client, self.host, self.port, ssl=ssl_context
            )
        else :
            self.server = await asyncio.start_server(
                self._handle_client, self.host, self.port
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
        tcpHandler = TcpHandler(reader, writer, trust=self.trust)
        print(f"[TcpServer] {tcpHandler.addr} Client connected")
        self.onConnected(tcpHandler)
