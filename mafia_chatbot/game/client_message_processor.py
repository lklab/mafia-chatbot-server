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

        self.client.subscribeMessage(
            msgType=messageTypeDict[game_pb2.RequestGameState],
            listener=self._onRequestGameStateMessage,
        )

    def _onRequestGameStateMessage(self, message: game_pb2.RequestGameState) :
        response = self.gameState.toProtoGameStateMessage(self.player)
        response.rqid = message.rqid
        self.client.sendMessage(response)
