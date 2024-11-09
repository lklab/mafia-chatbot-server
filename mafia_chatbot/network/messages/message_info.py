from typing import Callable, Type, Any
from mafia_chatbot.network.messages import *

messageTypeDict: dict[Type, int] = {
    auth_pb2.Auth : 0,
    auth_pb2.AuthResponse : 1,
}

def _AuthMessageFactory(data: bytes) -> auth_pb2.Auth :
    message = auth_pb2.Auth()
    message.ParseFromString(data)
    return message

def _AuthResponseMessageFactory(data: bytes) -> auth_pb2.AuthResponse :
    message = auth_pb2.AuthResponse()
    message.ParseFromString(data)
    return message


messageFactoryDict: dict[int, Callable[[bytes], Any]] = {
    0 : _AuthMessageFactory,
    1 : _AuthResponseMessageFactory,
}
