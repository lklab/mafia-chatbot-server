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

        self.clients: set[TcpHandler] = set()

        self.isServing: bool = False
        self.isRestart: bool = False
        self.restartFuture: asyncio.Future = None

    async def start(self, onConnected: Callable[[TcpHandler], None]) :
        self.onConnected = onConnected
        await self._startServer()
        addr = self.server.sockets[0].getsockname()
        # print(f'[TcpServer] Server started on {addr}')

    async def serve(self) :
        if self.server :
            while True :
                try :
                    if self.restartFuture != None :
                        self.restartFuture.set_result(0)
                        self.restartFuture = None
                    self.isServing = True

                    await self.server.serve_forever()

                except asyncio.CancelledError :
                    print("[TcpServer] Server cancelled")

                if self.isRestart :
                    self.isRestart = False
                    try :
                        await self.server.wait_closed()
                        await self._startServer()
                    except Exception as e :
                        print(f"[TcpServer] fail to restart server: {e}")
                        break
                    except :
                        print(f"[TcpServer] fail to restart server")
                        break
                else :
                    break
        else :
            print("[TcpServer] Server has not been started yet. Please call start() first.")

    async def close(self) :
        if self.server :
            print("[TcpServer] Shutting down server...")
            self.isRestart = False
            self.isServing = False
            self.server.close()
            await self.server.wait_closed()
            print("[TcpServer] Server shut down complete.")
        else :
            print("[TcpServer] Server is not running.")

    async def restart(self) :
        if not self.isServing :
            return

        self.isRestart = True
        self.isServing = False

        self.server.close()

        for client in self.clients :
            asyncio.create_task(client.close())

        self.restartFuture = asyncio.Future()
        await self.restartFuture

    async def _startServer(self) :
        if self.useSSL :
            self.server = await asyncio.start_server(
                self._handle_client, self.host, self.port, ssl=self._getSslContext()
            )
        else :
            self.server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        tcpHandler = TcpHandler(reader, writer, trust=self.trust)
        self.clients.add(tcpHandler)
        tcpHandler.addOnDisconnected(lambda: self._onClientDisconnected(tcpHandler))
        # print(f"[TcpServer] {tcpHandler.addr} Client connected")
        self.onConnected(tcpHandler)

    def _getSslContext(self) :
        sslContext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslContext.load_cert_chain(
            certfile=server_config.getCertfile(),
            keyfile=server_config.getKeyfile(),
        )
        return sslContext

    def _onClientDisconnected(self, tcpHandler: TcpHandler) :
        self.clients.discard(tcpHandler)
