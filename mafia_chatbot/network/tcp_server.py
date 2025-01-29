import asyncio
import ssl
from typing import Callable
import os

from mafia_chatbot.network.tcp_handler import TcpHandler
import mafia_chatbot.utils.server_config as server_config

class TcpServer :
    def __init__(self, port: int, host: str = '0.0.0.0', useSSL: bool = True, trust: bool = False) :
        self.server = None
        self.host: str = host
        self.port: int = port
        self.useSSL: bool = useSSL
        self.trust: bool = trust

        self.sslContext = None
        self.certCheckTask: asyncio.Task = None

        if self.useSSL :
            self.certCheckTask = asyncio.create_task(self._certCheckTask())

    async def start(self, onConnected: Callable[[TcpHandler], None]) :
        self.onConnected = onConnected

        if self.useSSL :
            self._createSslContext()

            self.server = await asyncio.start_server(
                self._handle_client, self.host, self.port, ssl=self.sslContext
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
        else :
            print("[TcpServer] Server has not been started yet. Please call start() first.")

        if self.certCheckTask != None :
            self.certCheckTask.cancel()
            try :
                await self.certCheckTask
            except :
                pass
            print('@@@ certCheckTask terminated')

    async def close(self) :
        if self.server :
            print("[TcpServer] Shutting down server...")
            self.server.close()
            await self.server.wait_closed()
            print("[TcpServer] Server shut down complete.")
        else :
            print("[TcpServer] Server is not running.")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
        tcpHandler = TcpHandler(reader, writer, trust=self.trust)
        print(f"[TcpServer] {tcpHandler.addr} Client connected")
        self.onConnected(tcpHandler)

    async def _certCheckTask(self) :
        lastTime = min(os.path.getmtime(server_config.getCertfile()), os.path.getmtime(server_config.getKeyfile()))
        print(f'@@@ lastTime={lastTime}')

        while True :
            await asyncio.sleep(5)
            mTime = min(os.path.getmtime(server_config.getCertfile()), os.path.getmtime(server_config.getKeyfile()))
            if mTime > lastTime :
                print(f'@@@ cert: {os.path.getmtime(server_config.getCertfile())}, key: {os.path.getmtime(server_config.getKeyfile())}, mTime: {mTime}')
                try :
                    await self._reloadSslContext()
                    lastTime = max(os.path.getmtime(server_config.getCertfile()), os.path.getmtime(server_config.getKeyfile()))
                except Exception as e :
                    print(f'@@@ fail to _reloadSslContext: {e}')
                except :
                    print('@@@ fail to _reloadSslContext')

    def _createSslContext(self) :
        """새로운 SSL 컨텍스트를 생성하여 업데이트하는 내부 함수"""
        sslContext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslContext.load_cert_chain(
            certfile=server_config.getCertfile(),
            keyfile=server_config.getKeyfile(),
        )
        self.sslContext = sslContext

    async def _reloadSslContext(self) :
        """인증서 갱신 후 새로운 SSL 컨텍스트를 로드"""
        if not self.useSSL or not self.server :
            print("[TcpServer] SSL 사용 안 함 또는 서버가 실행되지 않음")
            return

        print("[TcpServer] Reloading SSL context...")
        self._createSslContext()

        # 이벤트 루프에서 SSL 컨텍스트를 안전하게 업데이트
        loop = self.server.get_loop()
        loop.call_soon_threadsafe(self._updateSslContext)
        print("[TcpServer] SSL context reloaded")

    def _updateSslContext(self) :
        """현재 실행 중인 서버에 새로운 SSL 컨텍스트 적용"""
        self.server._ssl_context = self.sslContext
        print('@@@ _ssl_context 변경 완료')
