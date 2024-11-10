from enum import Enum
import uuid

from mafia_chatbot.game.player_info import PlayerInfo

class ChatType(Enum) :
    SYSTEM = 0
    DISCUSSION = 1

class ChatData :
    def __init__(self, type: ChatType, index: int, content: str, sender: PlayerInfo = None, receiver: PlayerInfo = None) :
        self.type = type
        self.index = index
        self.content = content
        self.sender = sender
        self.receiver = receiver

        self.id: str = str(uuid.uuid4())
