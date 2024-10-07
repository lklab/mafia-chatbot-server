class GameInfo :
    def __init__(self,
        humanName: str,
        playerCount: int,
        mafiaCount: int,
        useLLM: bool = True) :

        self.humanName = humanName
        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount
        self.useLLM = useLLM
