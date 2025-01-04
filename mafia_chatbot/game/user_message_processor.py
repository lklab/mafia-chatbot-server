from mafia_chatbot.game.game_state import GameState, Phase, VoteData
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import Role
from mafia_chatbot.game.strategy import VoteStrategy
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.game_logger import GameLogger, TAG

from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse

class UserMessageProcessor :
    def __init__(self, gameState: GameState, trustRecorder: TrustRecorder, player: Player) :
        self.gameState = gameState
        self.logger: GameLogger = gameState.logger
        self.trustRecorder = trustRecorder
        self.player = player
        self.user: ClientUser = player.user

        listeners = {
            game_pb2.RequestGameState : self._onRequestGameStateMessage,
            game_pb2.RequestChatList : self._onRequestChatListMessage,
            game_pb2.RequestAddChat : self._onRequestAddChatMessage,
            game_pb2.GetChat : self._onGetChatMessage,
            game_pb2.SetTarget : self._onSetTargetMessage,
            game_pb2.GetVoteState : self._onGetVoteStateMessage,
        }

        for msgType, listener in listeners.items() :
            self.user.subscribeMessage(
                msgType=msgType,
                listener=listener,
            )

    def _onRequestGameStateMessage(self, message: game_pb2.RequestGameState) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received RequestGameState: message=<{message}>')
        response = self.gameState.toProtoGameStateMessage(self.player)
        response.rqid = message.rqid
        self.user.send(response)

    def _onRequestChatListMessage(self, message: game_pb2.RequestChatList) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received RequestChatList: message=<{message}>')
        response = game_pb2.ChatList()
        response.rqid = message.rqid
        response.chats.extend(list(map(lambda chat : chat.createProtoMessage(self.player.info), self.gameState.chatList)))
        self.user.send(response)

    def _onRequestAddChatMessage(self, message: game_pb2.RequestAddChat) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received RequestAddChat: message=<{message}>')

        # check am I live
        if not self.player.isLive :
            errorResponse = self._makeErrorResponse(message, 0, 'You are not allowed to do that.')
            self.user.send(errorResponse)
            return

        # check remain chat count
        if self.player.remainChatingCount <= 0 :
            errorResponse = self._makeErrorResponse(message, 0, 'Chat count exceeded.')
            self.user.send(errorResponse)
            return

        # check sender
        if self.player.info.id != message.chat.sender :
            errorResponse = self._makeErrorResponse(message, 0, 'The sender id is incorrect.')
            self.user.send(errorResponse)
            return

        # check phase
        if self.gameState.currentPhase != Phase.DAY :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid phase.')
            self.user.send(errorResponse)
            return

        # check content length
        contentLength = len(message.chat.content)
        if contentLength > 200 :
            errorResponse = self._makeErrorResponse(message, 0, 'The content exceeds 200 characters.')
            self.user.send(errorResponse)
            return

        self.player.remainChatingCount -= 1

        response = game_pb2.AddChat()
        response.rqid = message.rqid
        response.chat.CopyFrom(message.chat)
        response.remainMyChat = self.player.remainChatingCount
        response.maxMyChat = self.player.maxChatingCount

        self.gameState.addHumanChat(self.player.info, response.chat)

        self.user.send(response)

    def _onGetChatMessage(self, message: game_pb2.GetChat) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received GetChat: message=<{message}>')

        index: int = message.index

        if index < 0 or index >= len(self.gameState.chatList) :
            errorResponse = self._makeErrorResponse(message, 0, 'There is no chat corresponding to the index.')
            self.user.send(errorResponse)
            return

        response = game_pb2.AddChat()
        response.rqid = message.rqid
        self.gameState.chatList[index].toProtoMessage(self.player.info, response.chat)
        response.remainMyChat = self.player.remainChatingCount
        response.maxMyChat = self.player.maxChatingCount
        self.user.send(response)

    _switchSetTargetCheckPhase = {
        game_data_pb2.TargetType.TARGET_VOTE : Phase.EVENING,
        game_data_pb2.TargetType.TARGET_KILL : Phase.NIGHT,
        game_data_pb2.TargetType.TARGET_TEST : Phase.NIGHT,
        game_data_pb2.TargetType.TARGET_HEAL : Phase.NIGHT,
    }

    _switchSetTargetCheckRole = {
        game_data_pb2.TargetType.TARGET_KILL : Role.MAFIA,
        game_data_pb2.TargetType.TARGET_TEST : Role.POLICE,
        game_data_pb2.TargetType.TARGET_HEAL : Role.DOCTOR,
    }

    def _switchSetTargetProcessVote(self, target: Player) :
        strategy: VoteStrategy = VoteStrategy(target.info)
        self.gameState.getCurrentVoteData().setVoteStrategy(self.player, strategy)
        self.trustRecorder.voteStrategyUpdated(self.player.info, strategy)

    def _switchSetTargetProcessKill(self, target: Player) :
        self.gameState.getCurrentNightTargetData().killTarget = target

    def _switchSetTargetProcessTest(self, target: Player) :
        self.gameState.getCurrentNightTargetData().testTarget = target

    def _switchSetTargetProcessHeal(self, target: Player) :
        self.gameState.getCurrentNightTargetData().healTarget = target

    _switchSetTargetProcess = {
        game_data_pb2.TargetType.TARGET_VOTE : _switchSetTargetProcessVote,
        game_data_pb2.TargetType.TARGET_KILL : _switchSetTargetProcessKill,
        game_data_pb2.TargetType.TARGET_TEST : _switchSetTargetProcessTest,
        game_data_pb2.TargetType.TARGET_HEAL : _switchSetTargetProcessHeal,
    }

    def _onSetTargetMessage(self, message: game_pb2.SetTarget) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received SetTarget: message=<{message}>')

        # check am I live
        if not self.player.isLive :
            errorResponse = self._makeErrorResponse(message, 0, 'You are not allowed to do that.')
            self.user.send(errorResponse)
            return

        # check is type valid
        if message.type == game_data_pb2.TargetType.TARGET_UNKNOWN :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid type.')
            self.user.send(errorResponse)
            return

        # check phase
        if self.gameState.currentPhase != UserMessageProcessor._switchSetTargetCheckPhase[message.type] :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid phase.')
            self.user.send(errorResponse)
            return

        # check role
        if (
            message.type != game_data_pb2.TargetType.TARGET_VOTE and
            self.player.info.role != UserMessageProcessor._switchSetTargetCheckRole[message.type]
        ) :
            errorResponse = self._makeErrorResponse(message, 0, 'You are not allowed to do that.')
            self.user.send(errorResponse)
            return

        # check target
        target: Player = self.gameState.getPlayerById(message.target)
        if target == None :
            errorResponse = self._makeErrorResponse(message, 0, 'There is no Player corresponding to ID.')
            self.user.send(errorResponse)
            return
        if not target.isLive :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid target.')
            self.user.send(errorResponse)
            return

        # process
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received SetTarget: type={message.type}, target={target.info.name}')
        UserMessageProcessor._switchSetTargetProcess[message.type](self, target)

        # response
        response = game_pb2.SetTargetResponse()
        response.rqid = message.rqid
        self.user.send(response)

    def _onGetVoteStateMessage(self, message: game_pb2.GetVoteState) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received GetVoteState: message=<{message}>')

        # check phase
        if self.gameState.currentPhase != Phase.EVENING :
            errorResponse = self._makeErrorResponse(message, 0, 'Not a valid phase.')
            self.user.send(errorResponse)
            return

        # response
        voteData: VoteData = self.gameState.getCurrentVoteData()
        response = voteData.getVoteStateMessage()
        response.rqid = message.rqid
        self.user.send(response)

    def _makeErrorResponse(self, message, code: int, detail: str) :
        self.logger.log(TAG.ERROR, f'[UserMessageProcessor] {self.player.info.name}: response error message: code={code}, detail={detail}')
        self.logger.log(TAG.ERROR, f'[UserMessageProcessor] {self.player.info.name}: received message: {message}')

        return makeErrorResponse(message, code, detail)
