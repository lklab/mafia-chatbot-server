ROLE_CITIZEN = 0
ROLE_MAFIA = 1
ROLE_POLICE = 2
ROLE_DOC = 3

roleToStr = {
    ROLE_CITIZEN: 'Citizen',
    ROLE_MAFIA: 'Mafia',
    ROLE_POLICE: 'Police',
    ROLE_DOC: 'Doctor',
}

class Player :
    def __init__(self, name, isAI) :
        self.name = name
        self.isAI = isAI
        self.role = ROLE_CITIZEN

        self.publicRole = ROLE_CITIZEN
        self.currentTargets = []
        self.pastTargets = []
        self.strategy = None

    def __str__(self) :
        return self.name

    def __repr__(self) :
        return f'{self.name}({roleToStr[self.role]})'
