from mafia_chatbot.game.game_state import GameState, Phase, VoteData
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import Role
from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.strategy import VoteStrategy

from mafia_chatbot.network.messages import *
from mafia_chatbot.network.messages.message_info import messageTypeDict

class ClientMessageProcessor :
    def __init__(self, gameState: GameState, player: Player) :
        self.gameState = gameState
        self.player = player
        self.client: ClientPlayer = player.client

        listeners = {
            game_pb2.RequestGameState : self._onRequestGameStateMessage,
            game_pb2.RequestChatList : self._onRequestChatListMessage,
            game_pb2.RequestAddChat : self._onRequestAddChatMessage,
            game_pb2.GetChat : self._onGetChatMessage,
            game_pb2.SetTarget : self._onSetTargetMessage,
            game_pb2.GetVoteState : self._onGetVoteStateMessage,
        }

        for msgType, listener in listeners.items() :
            self.client.subscribeMessage(
                msgType=msgType,
                listener=listener,
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
        # check am I live
        if not self.player.isLive :
            errorResponse = self._makeErrorResponse(message, 0, 'You are not allowed to do that.')
            self.client.sendMessage(errorResponse)
            return

        # check remain chat count
        if self.player.remainChatingCount <= 0 :
            errorResponse = self._makeErrorResponse(message, 0, 'Chat count exceeded.')
            self.client.sendMessage(errorResponse)
            return

        # check sender
        if self.player.info.id != message.chat.sender :
            errorResponse = self._makeErrorResponse(message, 0, 'The sender id is incorrect.')
            self.client.sendMessage(errorResponse)
            return

        self.player.remainChatingCount -= 1

        chat: game_pb2.Chat = self.gameState.addHumanChat(self.player.info, message.chat)
        response = game_pb2.AddChat()
        response.rqid = message.rqid
        response.chat.CopyFrom(chat)
        response.remainMyChat = self.player.remainChatingCount
        response.maxMyChat = self.player.maxChatingCount
        self.client.sendMessage(response)

    def _onGetChatMessage(self, message: game_pb2.GetChat) :
        index: int = message.index

        if index < 0 or index >= len(self.gameState.chatList) :
            errorResponse = self._makeErrorResponse(message, 0, 'There is no chat corresponding to the index.')
            self.client.sendMessage(errorResponse)
            return

        response = game_pb2.AddChat()
        response.rqid = message.rqid
        response.chat.CopyFrom(self.gameState.chatList[index].toProtoMessage(self.player.info))
        response.remainMyChat = self.player.remainChatingCount
        response.maxMyChat = self.player.maxChatingCount
        self.client.sendMessage(response)

    _switchSetTargetCheckPhase = {
        game_pb2.TargetType.TARGET_VOTE : Phase.EVENING,
        game_pb2.TargetType.TARGET_KILL : Phase.NIGHT,
        game_pb2.TargetType.TARGET_TEST : Phase.NIGHT,
        game_pb2.TargetType.TARGET_HEAL : Phase.NIGHT,
    }

    _switchSetTargetCheckRole = {
        game_pb2.TargetType.TARGET_KILL : Role.MAFIA,
        game_pb2.TargetType.TARGET_TEST : Role.POLICE,
        game_pb2.TargetType.TARGET_HEAL : Role.DOCTOR,
    }

    def _switchSetTargetProcessVote(self, target: Player) :
        strategy: VoteStrategy = VoteStrategy(target.info)
        self.gameState.getCurrentVoteData().setVoteStrategy(self.player, strategy)

    def _switchSetTargetProcessKill(self, target: Player) :
        self.gameState.getCurrentNightTargetData().killTarget = target

    def _switchSetTargetProcessTest(self, target: Player) :
        self.gameState.getCurrentNightTargetData().testTarget = target

    def _switchSetTargetProcessHeal(self, target: Player) :
        self.gameState.getCurrentNightTargetData().healTarget = target

    _switchSetTargetProcess = {
        game_pb2.TargetType.TARGET_VOTE : _switchSetTargetProcessVote,
        game_pb2.TargetType.TARGET_KILL : _switchSetTargetProcessKill,
        game_pb2.TargetType.TARGET_TEST : _switchSetTargetProcessTest,
        game_pb2.TargetType.TARGET_HEAL : _switchSetTargetProcessHeal,
    }

    def _onSetTargetMessage(self, message: game_pb2.SetTarget) :
        # check am I live
        if not self.player.isLive :
            errorResponse = self._makeErrorResponse(message, 0, 'You are not allowed to do that.')
            self.client.sendMessage(errorResponse)
            return

        # check is type valid
        if message.type == game_pb2.TargetType.TARGET_UNKNOWN :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid type.')
            self.client.sendMessage(errorResponse)
            return

        # check phase
        if self.gameState.currentPhase != ClientMessageProcessor._switchSetTargetCheckPhase[message.type] :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid phase.')
            self.client.sendMessage(errorResponse)
            return

        # check role
        if (
            message.type != game_pb2.TargetType.TARGET_VOTE and
            self.player.info.role != ClientMessageProcessor._switchSetTargetCheckRole[message.type]
        ) :
            errorResponse = self._makeErrorResponse(message, 0, 'You are not allowed to do that.')
            self.client.sendMessage(errorResponse)
            return

        # check target
        target: Player = self.gameState.getPlayerById(message.target)
        if target == None :
            errorResponse = self._makeErrorResponse(message, 0, 'There is no Player corresponding to ID.')
            self.client.sendMessage(errorResponse)
            return
        if not target.isLive :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid target.')
            self.client.sendMessage(errorResponse)
            return

        # process
        ClientMessageProcessor._switchSetTargetProcess[message.type](self, target)

        # response
        response = game_pb2.SetTargetResponse()
        response.rqid = message.rqid
        self.client.sendMessage(response)

    def _onGetVoteStateMessage(self, message: game_pb2.GetVoteState) :
        # check phase
        if self.gameState.currentPhase != Phase.EVENING :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid phase.')
            self.client.sendMessage(errorResponse)
            return

        # response
        voteData: VoteData = self.gameState.getCurrentVoteData()
        response = voteData.getVoteStateMessage()
        response.rqid = message.rqid
        self.client.sendMessage(response)

    def _makeErrorResponse(self, message, code: int, detail: str) :
        print(f'@@@ error response: {detail}')
        errorResponse = error_pb2.RequestError()
        errorResponse.rqid = message.rqid
        errorResponse.rqtype = messageTypeDict[type(message)]
        errorResponse.code = code
        errorResponse.detail = detail
        return errorResponse
