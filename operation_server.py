import asyncio
from typing import Any

from mafia_chatbot.firebase import firebase

from mafia_chatbot.network.client_handler import ClientHandler
from mafia_chatbot.network.client_server import ClientServer
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.message_handler import MessageHandler
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import ErrorCode, makeErrorResponse

from mafia_chatbot.operation.operation_manager import operationManager

from mafia_chatbot.utils.wands_logger import WandsLogger

OPERATION_PORT = 10011

class OperationServer :
    def __init__(self) :
        self.logger = WandsLogger('network', 'operation')

    async def run(self) :
        operationManager.initialize()
        firebase.initialize()

        self.server = ClientServer(
            port=OPERATION_PORT,
            onAuth=self._onClientAuth,
            onMessage=self._onClientMessage,
            onDisconnected=self._onClientDisconnected,
            logger=self.logger,
        )
        await self.server.start()
        await self.server.serve()

    def _onClientAuth(self, user: ClientUser, messageHandler: MessageHandler, message) -> tuple[Any, bool] :
        self.logger.debug(f'_onClientAuth clientId={user.clientId}')
        return None, True

    def _onClientMessage(self, client: ClientHandler, message) :
        self.logger.debug(f'_onClientMessage clientId={client.user.clientId} name={client.user.clientName}, type={type(message)}, message=<{message}>')
        if type(message) in OperationServer._switchClientMessage :
            OperationServer._switchClientMessage[type(message)](self, client, message)
        else :
            errorResponse = makeErrorResponse(message, ErrorCode.BAD_REQUEST, f'Cannot process the message.')
            self._respondToClient(client, errorResponse, isError=True)

    def _onClientDisconnected(self, client: ClientHandler) :
        if client.user != None :
            self.logger.debug(f'_onClientDisconnected clientId={client.user.clientId} name={client.user.clientName}')

    def _switchClientMessageGetServerState(self, client: ClientHandler, message) :
        response = operation_pb2.ServerState()
        response.rqid = message.rqid
        response.operating = operationManager.operating
        response.stateMessage = operationManager.getStateMessage(message.language)
        self._respondToClient(client, response)

    _switchClientMessage = {
        operation_pb2.GetServerState : _switchClientMessageGetServerState,
    }

    def _respondToClient(self, client: ClientHandler, message, isError: bool = False) :
        if isError :
            self.logger.error(f'_respondToClient id={client.user.clientId}, name={client.user.clientName}, type={type(message)}, message=<{message}>')
        else :
            self.logger.debug(f'_respondToClient id={client.user.clientId}, name={client.user.clientName}, type={type(message)}, message=<{message}>')
        client.respond(message)

if __name__ == "__main__" :
    server = OperationServer()
    asyncio.run(server.run())
