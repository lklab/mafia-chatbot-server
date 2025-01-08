from mafia_chatbot.game.player_info import Role, protoToRoleDict

from mafia_chatbot.network.client_user import ClientUser
from mafia_chatbot.network.messages import *

from mafia_chatbot.utils.name_bank import isSupportedLanguage

def varifyGameInfo(info: game_data_pb2.GameInfo) -> bool :
    if info.playerCount > 10 or info.playerCount < 3 :
        return False

    if info.playerCount <= info.mafiaCount * 2 :
        return False

    if info.mafiaCount <= 0 :
        return False

    if not isSupportedLanguage(info.language.lower()) :
        return False

    return True

class DebugInfo :
    def __init__(self, data: game_data_pb2.DebugInfo) :
        self.fixedRole: Role = protoToRoleDict[data.fixedRole]
        self.fixedRoleClientId: str = data.fixedRoleClientId

        self.daySeconds: int = data.daySeconds
        self.eveningSeconds: int = data.eveningSeconds
        self.nightSeconds: int = data.nightSeconds

        self.useLLM: bool = data.useLLM

        self.nonTargetableClientId: str = data.nonTargetableClientId
        self.observerClientId: str = data.observerClientId
        self.continueOnlyBots: bool = data.continueOnlyBots

class GameInfo :
    def __init__(self,
        gameId: str,
        playerCount: int,
        mafiaCount: int,
        users: list[ClientUser],
        localPlayerName: str,
        language: str = 'english',
        debugInfo: DebugInfo = None) :

        self.gameId = gameId

        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount

        self.users = users or []
        self.localPlayerName = localPlayerName

        self.language = language.lower()

        self.useLLM = True
        self.isCUI = localPlayerName != None

        self.debugInfo = None
        if debugInfo != None :
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

        humanCount: int = len(self.users)
        if (self.localPlayerName != None) :
            humanCount += 1

        if self.playerCount < humanCount :
            return False

        # TODO check language
        # TODO check duplicated names

        return True
