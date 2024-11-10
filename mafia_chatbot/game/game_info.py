from mafia_chatbot.game.client_player import ClientPlayer

class GameInfo :
    def __init__(self,
        playerCount: int,
        mafiaCount: int,
        clients: list[ClientPlayer],
        localPlayerName: str,
        language: str = 'english',
        useLLM: bool = True) :

        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount

        self.clients = clients or []
        self.localPlayerName = localPlayerName

        self.language = language
        self.useLLM = useLLM

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

        # TODO check language

        return True
