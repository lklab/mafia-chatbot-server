from enum import Enum
import uuid

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
    def __init__(self, name: str, tone: str, isHuman: bool) :
        self.id: str = str(uuid.uuid4())
        self.name: str = name
        self.tone: str = tone
        self.isHuman: bool = isHuman
        self.role: Role = Role.CITIZEN

    def __str__(self) :
        return self.name

    def __repr__(self) :
        return f'{self.name}({self.role.name})'
