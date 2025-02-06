from mafia_chatbot.game.player_info import Role

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
        fixedRole: Role = None,
        debugInfo: DebugInfo = None) :

        self.gameId = gameId

        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount

        self.users = users or []
        self.localPlayerName = localPlayerName

        self.language = language.lower()
        self.fixedRole = fixedRole if len(self.users) == 1 else None

        self.useLLM = True
        self.isCUI = localPlayerName != None

        self.debugInfo = None
        if debugInfo != None :
            self.debugInfo = debugInfo
            self.isCUI = True
            self.useLLM = debugInfo.useLLM
