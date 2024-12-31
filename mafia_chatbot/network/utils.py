from mafia_chatbot.network.messages import *
from mafia_chatbot.network.message_handler import messageTypeDict

def makeErrorResponse(message, code: int, detail: str) :
    errorResponse = error_pb2.RequestError()
    errorResponse.rqid = message.rqid
    errorResponse.rqtype = messageTypeDict[type(message)]
    errorResponse.code = code
    errorResponse.detail = detail
    return errorResponse
