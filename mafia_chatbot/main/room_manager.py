from mafia_chatbot.main.room import Room, validateCreateRoomMessage

from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse, MessageException
from mafia_chatbot.network.client_user import ClientUser

from mafia_chatbot.utils.wands_logger import WandsLogger
from mafia_chatbot.utils.code_generator import CodeGenerator

class RoomManager :
    def __init__(self, logger: WandsLogger) :
        self.logger = logger

        self.roomByClientId: dict[str, Room] = {}
        self.roomByCode: dict[str, Room] = {}
        self.codeGenerator: CodeGenerator = CodeGenerator(min_digits=4)

    def processMessageRequestMyRoomInfo(self, user: ClientUser, message) :
        message = room_pb2.MyRoomInfo()
        message.rqid = message.rqid

        if user.clientId in self.roomByClientId :
            message.isRoomExists = True
            self.roomByClientId[user.clientId].infoToProtoMessage(message.info)
        else :
            message.isRoomExists = False

        self._sendToUser(message)

    def processMessageCreateRoom(self, user: ClientUser, message) :
        if user.isNeedToSignUp() :
            errorResponse = makeErrorResponse(message, 0, 'The player has not been fully configured.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        if user.clientId in self.roomByClientId :
            errorResponse = makeErrorResponse(message, 0, 'You are already participating in another room.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        if not validateCreateRoomMessage(message) :
            errorResponse = makeErrorResponse(message, 0, 'The room information is invalid.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        code: str = self.codeGenerator.issueCode()
        room = Room(message, code, user, self.logger, self._onRoomDestroyed)
        self.roomByClientId[user.clientId] = room
        self.roomByCode[code] = room

        response = room_pb2.CreateRoomResponse()
        response.rqid = message.rqid
        room.infoToProtoMessage(response.roomInfo)
        self._sendToUser(user, response)

    def processMessageJoinRoom(self, user: ClientUser, message) :
        if user.isNeedToSignUp() :
            errorResponse = makeErrorResponse(message, 0, 'The player has not been fully configured.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        if user.clientId in self.roomByClientId :
            errorResponse = makeErrorResponse(message, 0, 'You are already participating in another room.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        if message.code not in self.roomByCode :
            errorResponse = makeErrorResponse(message, 0, 'No room matches the provided code.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        room: Room = self.roomByCode[message.code]

        try :
            room.join(user, message.password)
        except MessageException as e :
            errorResponse = e.makeResponse(message)
            self._sendToUser(user, errorResponse, isError=True)
            return

        self.roomByClientId[user.clientId] = room

        response = room_pb2.JoinRoomResponse()
        response.rqid = message.rqid
        room.infoToProtoMessage(response.roomInfo)
        self._sendToUser(user, response)

    def processMessageQuitRoom(self, user: ClientUser, message) :
        if user.clientId not in self.roomByClientId :
            errorResponse = makeErrorResponse(message, 0, 'You are not participating in any room.')
            self._sendToUser(user, errorResponse, isError=True)
            return

        room: Room = self.roomByClientId[user.clientId]

        try :
            room.quit(user)
        except MessageException as e :
            errorResponse = e.makeResponse(message)
            self._sendToUser(user, errorResponse, isError=True)
            return

        del self.roomByClientId[user.clientId]

        response = room_pb2.QuitRoomResponse()
        response.rqid = message.rqid
        self._sendToUser(user, response)

    def destroyRoom(self, code: str) :
        if code in self.roomByCode :
            room: Room = self.roomByCode[code]
            room.destroy()
            self._onRoomDestroyed(room)

    def _onRoomDestroyed(self, room: Room) :
        self.codeGenerator.returnCode(room.code)

        for user in room.users :
            if user.clientId in self.roomByClientId :
                del self.roomByClientId[user.clientId]
        if room.code in self.roomByCode :
            del self.roomByCode[room.code]

    def _sendToUser(self, user: ClientUser, message, isError: bool = False) :
        if isError :
            self.logger.error(f'[RoomManager] _sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        else :
            self.logger.debug(f'[RoomManager] _sendToUser id={user.clientId}, name={user.clientName}, type={type(message)}, message=<{message}>')
        user.send(message)
