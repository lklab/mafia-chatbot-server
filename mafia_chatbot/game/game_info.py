from enum import Enum

from mafia_chatbot.game.client_player import ClientPlayer

class GameMode(Enum) :
    CUI = 0
    CUI_WITH_LLM = 1
    CLIENT = 2

class GameInfo :
    def __init__(self,
        playerCount: int,
        mafiaCount: int,
        clients: list[ClientPlayer],
        localPlayerName: str,
        language: str = 'english',
        gameMode: GameMode = GameMode.CUI_WITH_LLM) :

        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount

        self.clients = clients or []
        self.localPlayerName = localPlayerName

        self.language = language

        self.gameMode = gameMode
        self.useLLM = gameMode != GameMode.CUI
        self.isCUI = gameMode != GameMode.CLIENT

    def checkValid(self) -> bool :
        if self.playerCount > 10 or self.playerCount < 3 :
            return False

        if self.playerCount <= self.mafiaCount * 2 :
            return False

        humanCount: int = len(self.clients)
        if (self.localPlayerName != None) :
            humanCount += 1

        if self.playerCount < humanCount :
            return False

        if self.isCUI :
            if len(self.clients) > 0 or self.localPlayerName == None :
                return False

        # TODO check language

        return True
