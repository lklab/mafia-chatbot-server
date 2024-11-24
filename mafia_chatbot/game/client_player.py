from typing import Callable, Any

from mafia_chatbot.network.message_client_handler import MessageClientHandler

class ClientPlayer :
    def __init__(self, id: str, name: str, client: MessageClientHandler) :
        self.id = id
        self.name = name
        self.client = client

        self.subscribers: dict[type, Callable[[Any], None]] = {}

    def forwardMessage(self, message: Any) :
        msgType = type(message)
        if msgType in self.subscribers :
            self.subscribers[msgType](message)
            return True
        else :
            return False

    def subscribeMessage(self, msgType: type, listener: Callable[[Any], None]) :
        self.subscribers[msgType] = listener

    def sendMessage(self, message: Any) :
        self.client.send(message)

    def clearSubscribers(self) :
        self.subscribers.clear()
