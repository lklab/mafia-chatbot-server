from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.client_player import ClientPlayer

from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

class ClientMessageProcessor :
    def __init__(self, gameState: GameState, player: Player) :
        self.gameState = gameState
        self.player = player
        self.client: ClientPlayer = player.client

        for msgType, listener in ClientMessageProcessor._listeners.items() :
            self.client.subscribeMessage(
                msgType=messageTypeDict[msgType],
                listener=lambda message : listener(self, message),
            )

    def _onRequestGameStateMessage(self, message: game_pb2.RequestGameState) :
        response = self.gameState.toProtoGameStateMessage(self.player)
        response.rqid = message.rqid
        self.client.sendMessage(response)

    def _onRequestChatListMessage(self, message: game_pb2.RequestChatList) :
        response = game_pb2.ChatList()
        response.rqid = message.rqid
        response.chats.extend(list(map(lambda chat : chat.toProtoMessage(self.player.info), self.gameState.chatList)))
        self.client.sendMessage(response)

    def _onRequestAddChatMessage(self, message: game_pb2.RequestAddChat) :
        # check remain chat count
        if self.player.remainChatingCount <= 0 :
            errorResponse = error_pb2.RequestError()
            errorResponse.rqid = message.rqid
            errorResponse.rqtype = messageTypeDict[type(message)]
            errorResponse.code = 0
            errorResponse.detail = 'Chat count exceeded.'
            self.client.sendMessage(errorResponse)
            return

        # check sender
        if self.player.info.id != message.sender :
            errorResponse = error_pb2.RequestError()
            errorResponse.rqid = message.rqid
            errorResponse.rqtype = messageTypeDict[type(message)]
            errorResponse.code = 0
            errorResponse.detail = 'The sender id is incorrect.'
            self.client.sendMessage(errorResponse)
            return

        chat: game_pb2.Chat = self.gameState.addHumanChat(self.player.info, message.chat)
        response = game_pb2.AddChat()
        response.rqid = message.rqid
        response.chat.CopyFrom(chat)
        response.remainMyChat = self.player.remainChatingCount
        self.client.sendMessage(response)

    def _onGetChatMessage(self, message: game_pb2.GetChat) :
        index: int = message.index

        if index < 0 or index >= len(self.gameState.chatList) :
            errorResponse = error_pb2.RequestError()
            errorResponse.rqid = message.rqid
            errorResponse.rqtype = messageTypeDict[type(message)]
            errorResponse.code = 0
            errorResponse.detail = 'There is no chat corresponding to the index.'
            self.client.sendMessage(errorResponse)
            return

        response = game_pb2.AddChat()
        response.rqid = message.rqid
        response.chat.CopyFrom(self.gameState.chatList[index].toProtoMessage(self.player.info))
        response.remainMyChat = self.player.remainChatingCount
        self.client.sendMessage(response)

    _listeners = {
        game_pb2.RequestGameState : _onRequestGameStateMessage,
        game_pb2.RequestChatList : _onRequestChatListMessage,
        game_pb2.RequestAddChat : _onRequestAddChatMessage,
        game_pb2.GetChat : _onGetChatMessage,
    }
