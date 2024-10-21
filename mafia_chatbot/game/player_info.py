from enum import Enum

class Role :
    pass

class Role(Enum) :
    CITIZEN = 0
    MAFIA = 1
    POLICE = 2
    DOCTOR = 3

strToRoleDict: dict[str, Role] = {
    'citizen': Role.CITIZEN,
    'police': Role.POLICE,
    'mafia': Role.MAFIA,
    'doctor': Role.DOCTOR,
}

def strToRole(roleStr: str) -> Role :
    if roleStr in strToRoleDict :
        return strToRoleDict[roleStr]
    return None

class PlayerInfo :
    def __init__(self, name: str, isAI: bool, tone: str) :
        self.name: str = name
        self.isAI: bool = isAI
        self.tone: str = tone
        self.role: Role = Role.CITIZEN

    def __str__(self) :
        return self.name

    def __repr__(self) :
        return f'{self.name}({self.role.name})'
