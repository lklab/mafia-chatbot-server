from enum import Enum
import uuid

from mafia_chatbot.game.player_info import PlayerInfo

from mafia_chatbot.network.messages import *

class ChatType(Enum) :
    SYSTEM = 0
    DISCUSSION = 1

chatTypeToProtoDict: dict[ChatType, game_data_pb2.ChatType] = {
    ChatType.SYSTEM: game_data_pb2.ChatType.CHAT_SYSTEM,
    ChatType.DISCUSSION: game_data_pb2.ChatType.CHAT_DISCUSSION,
}

class ChatData :
    def __init__(self,
                 type: ChatType,
                 index: int,
                 content: str,
                 sender: PlayerInfo = None,
                 receiver: PlayerInfo = None,
                 id: str = None,
        ) :
        self.type = type
        self.index = index
        self.content = content
        self.sender = sender
        self.receiver = receiver

        if id != None :
            self.id = id
        else :
            self.id: str = str(uuid.uuid4())

    def createProtoMessage(self, receiver: PlayerInfo) -> game_data_pb2.Chat :
        message = game_data_pb2.Chat()
        self.toProtoMessage(receiver, message)
        return message

    def toProtoMessage(self, receiver: PlayerInfo, chat_out: game_data_pb2.Chat) :
        chat_out.id = self.id
        chat_out.type = chatTypeToProtoDict[self.type]
        chat_out.index = self.index
        chat_out.sender = self.sender.id if self.sender != None else ''

        if self.type == ChatType.DISCUSSION or self.receiver == None or self.receiver.id == receiver.id :
            chat_out.content = self.content
        else :
            chat_out.content = ''
