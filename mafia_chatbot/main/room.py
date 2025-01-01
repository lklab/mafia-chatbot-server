import random
from typing import Callable
import asyncio

from mafia_chatbot.network.messages import *
from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.utils import MessageException

from mafia_chatbot.utils.wands_logger import WandsLogger

def validateCreateRoomMessage(message: room_pb2.CreateRoom) -> bool :
    if (
        message.maxHumans <= 0 or
        message.maxHumans >= 11 or
        len(message.password) >= 11
    ) :
        return False

    return True

class Room :
    pass

class Room :
    def __init__(self, createRoomMessage: room_pb2.CreateRoom, code: str, hostUser: ClientUser, logger: WandsLogger, onDestroy: Callable[[Room], None]) :
        self.language: str = createRoomMessage.language
        self.maxHumans: int = createRoomMessage.maxHumans
        self.password: str = createRoomMessage.password

        self.code: str = code

        self.hostUser: ClientUser = hostUser
        self.users: list[ClientUser] = [hostUser]
        hostUser.addRef()

        self.logger = logger
        self.onDestroy = onDestroy

        self.timeoutTask = asyncio.create_task(self._timeoutTerminate(3600))
        self.isDestroyed = False

    def join(self, user: ClientUser, password: str) :
        if self.isDestroyed :
            raise MessageException(0, 'This room has already expired.')

        if user in self.users :
            raise MessageException(0, 'You are already participating in this room.')

        if self.password != password :
            raise MessageException(0, 'The password does not match.')

        if len(self.users) >= self.maxHumans :
            raise MessageException(0, 'This room is full.')

        user.addRef()
        self.users.append(user)
        self._sendInfoToAllUsers()

    def quit(self, user: ClientUser) :
        if self.isDestroyed :
            raise MessageException(0, 'This room has already expired.')

        if user not in self.users :
            raise MessageException(0, 'You are not participating in this room.')

        self.users.remove(user)
        user.releaseRef()

        if user.clientId == self.hostUser.clientId :
            if len(self.users) > 0 :
                self.hostUser = random.choice(self.users)
                self._sendInfoToAllUsers()
            else :
                self.destroy()
                self.onDestroy(self)

    def destroy(self, sendMessage: bool = False) :
        if self.isDestroyed :
            return
        self.isDestroyed = True

        if self.timeoutTask != None :
            self.timeoutTask.cancel()
            self.timeoutTask = None

        for user in self.users :
            user.releaseRef()

        if sendMessage :
            self._sendDestroyedToAllUsers()

    def infoToProtoMessage(self, message: room_pb2.RoomInfo) :
        message.code = self.code
        message.language = self.language
        message.maxHumans = self.maxHumans
        message.participants.extend(list(map(lambda user : self._createParticipantMessage(user), self.users)))
        message.hostId = self.hostUser.clientId

    def _createParticipantMessage(self, user: ClientUser) :
        message = room_pb2.Participant()
        message.clientId = user.clientId
        message.name = user.clientName
        return message

    def _sendInfoToAllUsers(self) :
        message = room_pb2.RoomInfoUpdated()
        self.infoToProtoMessage(message.info)

        for user in self.users :
            user.send(message)

        self.logger.debug(f'[Room] _sendInfoToAllUsers type={type(message)}, message=<{message}>')

    def _sendDestroyedToAllUsers(self) :
        message = room_pb2.RoomDestroyed()

        for user in self.users :
            user.send(message)

        self.logger.debug(f'[Room] _sendDestroyedToAllUsers type={type(message)}, message=<{message}>')

    async def _timeoutTerminate(self, seconds: float) :
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError :
            return

        self.logger.error(f'room {self.code} terminated by timeout')
        self.timeoutTask = None
        self.destroy(sendMessage=True)
        self.onDestroy(self)
