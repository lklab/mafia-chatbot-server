from typing import Callable, Any

from mafia_chatbot.network.message_handler import MessageHandler

class ClientPlayer :
    def __init__(self, clientId: str, name: str) :
        self.clientId = clientId
        self.name = name

        self.subscribers: dict[type, Callable[[Any], None]] = {}

    def setMessageHandler(self, messageHandler: MessageHandler) :
        self.messageHandler = messageHandler

    def clearMessageHandler(self) :
        self.messageHandler = None

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
        if self.messageHandler != None :
            self.messageHandler.send(message)

    def clearSubscribers(self) :
        self.subscribers.clear()
