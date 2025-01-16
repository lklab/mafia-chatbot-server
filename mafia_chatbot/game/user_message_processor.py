from mafia_chatbot.game.game_state import GameState, Phase, VoteData, KillVoteData
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import Role
from mafia_chatbot.game.strategy import VoteStrategy
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.game_logger import GameLogger, TAG

from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.messages import *
from mafia_chatbot.network.utils import makeErrorResponse, ErrorCode
from mafia_chatbot.network.message_handler import MessageHandler

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
            game_pb2.CancelKillWithAds : self._onCancelKillWithAdsMessage,
        }

        for msgType, listener in listeners.items() :
            self.user.subscribeMessage(
                msgType=msgType,
                listener=listener,
            )

    def _onRequestGameStateMessage(self, messageHandler: MessageHandler, message: game_pb2.RequestGameState) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received RequestGameState: message=<{message}>')
        response = self.gameState.toProtoGameStateMessage(self.player)
        response.rqid = message.rqid
        self.user.respond(messageHandler, response)

    def _onRequestChatListMessage(self, messageHandler: MessageHandler, message: game_pb2.RequestChatList) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received RequestChatList: message=<{message}>')
        response = game_pb2.ChatList()
        response.rqid = message.rqid
        response.chats.extend(list(map(lambda chat : chat.createProtoMessage(self.player.info), self.gameState.chatList)))
        self.user.respond(messageHandler, response)

    def _onRequestAddChatMessage(self, messageHandler: MessageHandler, message: game_pb2.RequestAddChat) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received RequestAddChat: message=<{message}>')

        # check am I live
        if not self.player.isLive :
            errorResponse = self._makeErrorResponse(message, ErrorCode.NO_PERMISSION, 'You are not allowed to do that.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check remain chat count
        if self.player.remainChatingCount <= 0 :
            errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Chat count exceeded.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check sender
        if self.player.info.id != message.chat.sender :
            errorResponse = self._makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The sender id is incorrect.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check phase
        if self.gameState.currentPhase != Phase.DAY :
            errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid phase.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check content length
        contentLength = len(message.chat.content)
        if contentLength > 200 :
            errorResponse = self._makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The content exceeds 200 characters.')
            self.user.respond(messageHandler, errorResponse)
            return

        self.player.remainChatingCount -= 1

        response = game_pb2.AddChat()
        response.rqid = message.rqid
        response.chat.CopyFrom(message.chat)
        response.remainMyChat = self.player.remainChatingCount
        response.maxMyChat = self.player.maxChatingCount

        self.gameState.addHumanChat(self.player.info, response.chat)

        self.user.respond(messageHandler, response)

    def _onGetChatMessage(self, messageHandler: MessageHandler, message: game_pb2.GetChat) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received GetChat: message=<{message}>')

        index: int = message.index

        if index < 0 or index >= len(self.gameState.chatList) :
            errorResponse = self._makeErrorResponse(message, ErrorCode.NOT_FOUND, 'There is no chat corresponding to the index.')
            self.user.respond(messageHandler, errorResponse)
            return

        response = game_pb2.AddChat()
        response.rqid = message.rqid
        self.gameState.chatList[index].toProtoMessage(self.player.info, response.chat)
        response.remainMyChat = self.player.remainChatingCount
        response.maxMyChat = self.player.maxChatingCount
        self.user.respond(messageHandler, response)

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
        self.gameState.getCurrentNightTargetData().killVoteData.setKillTarget(self.player, target)

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

    def _onSetTargetMessage(self, messageHandler: MessageHandler, message: game_pb2.SetTarget) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received SetTarget: message=<{message}>')

        # check am I live
        if not self.player.isLive :
            errorResponse = self._makeErrorResponse(message, ErrorCode.NO_PERMISSION, 'You are not allowed to do that.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check is type valid
        if message.type == game_data_pb2.TargetType.TARGET_UNKNOWN :
            errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid type.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check phase
        if self.gameState.currentPhase != UserMessageProcessor._switchSetTargetCheckPhase[message.type] :
            errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid phase.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check role
        if (
            message.type != game_data_pb2.TargetType.TARGET_VOTE and
            self.player.info.role != UserMessageProcessor._switchSetTargetCheckRole[message.type]
        ) :
            errorResponse = self._makeErrorResponse(message, ErrorCode.NO_PERMISSION, 'You are not allowed to do that.')
            self.user.respond(messageHandler, errorResponse)
            return

        # check target
        target: Player = self.gameState.getPlayerById(message.target)
        if target == None :
            errorResponse = self._makeErrorResponse(message, ErrorCode.NOT_FOUND, 'There is no Player corresponding to ID.')
            self.user.respond(messageHandler, errorResponse)
            return
        if not target.isLive :
            errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid target.')
            self.user.respond(messageHandler, errorResponse)
            return

        # process
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received SetTarget: type={message.type}, target={target.info.name}')
        UserMessageProcessor._switchSetTargetProcess[message.type](self, target)

        # response
        response = game_pb2.SetTargetResponse()
        response.rqid = message.rqid
        self.user.respond(messageHandler, response)

    def _onGetVoteStateMessage(self, messageHandler: MessageHandler, message: game_pb2.GetVoteState) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received GetVoteState: message=<{message}>')

        # for vote
        if message.type == game_data_pb2.TargetType.TARGET_VOTE :
            # check phase
            if self.gameState.currentPhase != Phase.EVENING :
                errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid phase.')
                self.user.respond(messageHandler, errorResponse)
                return

            voteData: VoteData = self.gameState.getCurrentVoteData()
            response = voteData.getVoteStateMessage()
            response.rqid = message.rqid
            self.user.respond(messageHandler, response)

        # for kill
        elif message.type == game_data_pb2.TargetType.TARGET_KILL :
            # check role
            if self.player.info.role != Role.MAFIA :
                errorResponse = self._makeErrorResponse(message, ErrorCode.NO_PERMISSION, 'You are not allowed to do that.')
                self.user.respond(messageHandler, errorResponse)
                return

            # check phase
            if self.gameState.currentPhase != Phase.NIGHT :
                errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid phase.')
                self.user.respond(messageHandler, errorResponse)
                return

            killVoteData: KillVoteData = self.gameState.getCurrentNightTargetData().killVoteData
            response = killVoteData.getVoteStateMessage()
            response.rqid = message.rqid
            self.user.respond(messageHandler, response)

        # others: error
        else :
            errorResponse = self._makeErrorResponse(message, ErrorCode.INVALID_DATA, 'The target type is invalid.')
            self.user.respond(messageHandler, errorResponse)

    def _onCancelKillWithAdsMessage(self, messageHandler: MessageHandler, message: game_pb2.CancelKillWithAds) :
        self.logger.log(TAG.NETWORK, f'[UserMessageProcessor] {self.player.info.name}: received CancelKillWithAds: message=<{message}>')

        # check phase
        if self.gameState.currentPhase != Phase.NIGHT :
            errorResponse = self._makeErrorResponse(message, ErrorCode.BAD_REQUEST, 'Not a valid phase.')
            self.user.respond(messageHandler, errorResponse)
            return

        success = self.gameState.setKillCancelRequest(self.player, message)

        if success :
            response = game_pb2.CancelKillWithAdsResponse()
            response.rqid = message.rqid
            self.user.respond(messageHandler, response)
        else :
            errorResponse = self._makeErrorResponse(message, ErrorCode.NOT_FOUND, 'Canceling the assassination was not requested of you.')
            self.user.respond(messageHandler, errorResponse)

    def _makeErrorResponse(self, message, code: ErrorCode, detail: str) :
        self.logger.log(TAG.ERROR, f'[UserMessageProcessor] {self.player.info.name}: response error message: code={code.name}, detail={detail}')
        self.logger.log(TAG.ERROR, f'[UserMessageProcessor] {self.player.info.name}: received message: {message}')

        return makeErrorResponse(message, code, detail)
