from typing import Callable, Type, Any
from mafia_chatbot.network.messages import *

messageTypeDict: dict[Type, int] = {
    error_pb2.Error : 0,
    auth_pb2.Auth : 1000,
    auth_pb2.AuthResponse : 1001,
}

def _ErrorMessageFactory(data: bytes) -> error_pb2.Error :
    message = error_pb2.Error()
    message.ParseFromString(data)
    return message

def _AuthMessageFactory(data: bytes) -> auth_pb2.Auth :
    message = auth_pb2.Auth()
    message.ParseFromString(data)
    return message

def _AuthResponseMessageFactory(data: bytes) -> auth_pb2.AuthResponse :
    message = auth_pb2.AuthResponse()
    message.ParseFromString(data)
    return message


messageFactoryDict: dict[int, Callable[[bytes], Any]] = {
    0 : _ErrorMessageFactory,
    1000 : _AuthMessageFactory,
    1001 : _AuthResponseMessageFactory,
}
