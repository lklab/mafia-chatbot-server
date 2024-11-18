from enum import Enum
import uuid

from mafia_chatbot.game.player_info import PlayerInfo

from mafia_chatbot.network.messages import *

class ChatType(Enum) :
    SYSTEM = 0
    DISCUSSION = 1

chatTypeToProtoDict: dict[ChatType, game_pb2.ChatType] = {
    ChatType.SYSTEM: game_pb2.ChatType.CHAT_SYSTEM,
    ChatType.DISCUSSION: game_pb2.ChatType.CHAT_DISCUSSION,
}

class ChatData :
    def __init__(self, type: ChatType, index: int, content: str, sender: PlayerInfo = None, receiver: PlayerInfo = None) :
        self.type = type
        self.index = index
        self.content = content
        self.sender = sender
        self.receiver = receiver

        self.id: str = str(uuid.uuid4())

    def toProtoMessage(self, receiver: PlayerInfo) -> game_pb2.Chat :
        message = game_pb2.Chat()

        message.id = self.id
        message.type = chatTypeToProtoDict[self.type]
        message.index = self.index
        message.sender = self.sender.id if self.sender != None else ''

        if self.type == ChatType.DISCUSSION or self.receiver == None or self.receiver.id == receiver.id :
            message.content = self.content
        else :
            message.content = ''

        return message
