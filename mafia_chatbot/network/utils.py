from enum import Enum

from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

class ErrorCode(Enum) :
    BAD_REQUEST = 1000
    INVALID_DATA = 1001
    ALREADY_EXISTS = 1002
    NOT_FOUND = 1003
    NO_PERMISSION = 1004
    CANT_PROCESS = 1005
    BUSY = 1006
    SERVER_ERROR = 2000
    NOT_OPERATING = 2001
    NO_CHANGES = 3000

def makeErrorResponse(message, code: ErrorCode, detail: str) :
    errorResponse = error_pb2.RequestError()
    errorResponse.rqid = message.rqid
    errorResponse.rqtype = messageTypeDict[type(message)]
    errorResponse.code = code.value
    errorResponse.detail = detail
    return errorResponse

class MessageException(Exception):
    def __init__(self, code: ErrorCode, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def makeResponse(self, message) :
        return makeErrorResponse(message, self.code, self.detail)
