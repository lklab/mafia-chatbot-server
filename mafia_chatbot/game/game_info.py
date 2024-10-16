class GameInfo :
    def __init__(self,
        playerCount: int,
        mafiaCount: int,
        humanName: str,
        language: str = 'english',
        useLLM: bool = True) :

        self.playerCount = playerCount
        self.citizenCount = playerCount - mafiaCount
        self.mafiaCount = mafiaCount
        self.humanName = humanName
        self.language = language
        self.useLLM = useLLM
