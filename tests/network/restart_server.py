if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import asyncio
import ssl

import mafia_chatbot.utils.server_config as server_config

async def main() :
    while True :
        print('start_server')
        server = await asyncio.start_server(
            handle_client, '0.0.0.0', 30123, ssl=getSslContext()
        )
        print('create_task')
        asyncio.create_task(stopServer(server))
        print('serve_forever')
        try :
            await server.serve_forever()
        except asyncio.CancelledError :
            print('CancelledError')
        print('wait_closed')
        await server.wait_closed()
        print('end wait_closed')

async def stopServer(server: asyncio.Server) :
    await asyncio.sleep(5)
    print('close server 1')
    server.close()
    print('close server 2')

def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) :
    pass

def getSslContext() :
    sslContext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sslContext.load_cert_chain(
        certfile=server_config.getCertfile(),
        keyfile=server_config.getKeyfile(),
    )
    return sslContext

asyncio.run(main())
