from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.player_info import Role, protoToRoleDict
from mafia_chatbot.network.messages import *

class DebugInfo :
    def __init__(self, data: game_pb2.DebugInfo) :
        self.fixedRole: Role = protoToRoleDict[data.fixedRole]
        self.fixedRoleClientId: str = data.fixedRoleClientId

        self.daySeconds: int = data.daySeconds
        self.eveningSeconds: int = data.eveningSeconds
        self.nightSeconds: int = data.nightSeconds

        self.useLLM: bool = data.useLLM
        self.targetable: bool = data.targetable
        self.observer: bool = data.observer
        self.ghostMode: bool = data.ghostMode

class GameInfo :
    def __init__(self,
        playerCount: int,
        mafiaCount: int,
        clients: list[ClientPlayer],
        localPlayerName: str,
        language: str = 'english',
        debugInfo: DebugInfo = None) :

        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount

        self.clients = clients or []
        self.localPlayerName = localPlayerName

        self.language = language

        self.useLLM = True
        self.isCUI = localPlayerName != None

        self.debugInfo = None
        if debugInfo != None and debugInfo.isDebug :
            self.debugInfo = debugInfo
            self.isCUI = True

            self.useLLM = debugInfo.useLLM

    def checkValid(self) -> bool :
        if self.playerCount > 10 or self.playerCount < 3 :
            return False

        if self.playerCount <= self.mafiaCount * 2 :
            return False

        if self.mafiaCount <= 0 :
            return False

        humanCount: int = len(self.clients)
        if (self.localPlayerName != None) :
            humanCount += 1

        if self.playerCount < humanCount :
            return False

        # TODO check language

        return True
