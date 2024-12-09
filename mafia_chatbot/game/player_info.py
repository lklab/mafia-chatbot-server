from enum import Enum
import uuid

from mafia_chatbot.network.messages import *

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

roleToStrDict: dict[Role, str] = {
    Role.CITIZEN : 'citizen',
    Role.POLICE : 'police',
    Role.MAFIA : 'mafia',
    Role.DOCTOR : 'doctor',
}

roleToProtoDict: dict[Role, game_pb2.Role] = {
    Role.CITIZEN: game_pb2.Role.Role_CITIZEN,
    Role.POLICE: game_pb2.Role.Role_POLICE,
    Role.MAFIA: game_pb2.Role.Role_MAFIA,
    Role.DOCTOR: game_pb2.Role.Role_DOCTOR,
}

protoToRoleDict: dict[game_pb2.Role, Role] = {
    game_pb2.Role.Role_UNKNOWN: None,
    game_pb2.Role.Role_CITIZEN: Role.CITIZEN,
    game_pb2.Role.Role_POLICE: Role.POLICE,
    game_pb2.Role.Role_MAFIA: Role.MAFIA,
    game_pb2.Role.Role_DOCTOR: Role.DOCTOR,
}

def strToRole(roleStr: str) -> Role :
    if roleStr in strToRoleDict :
        return strToRoleDict[roleStr]
    return None

class PlayerInfo :
    def __init__(self, name: str, tone: str, isHuman: bool, isLocalPlayer: bool) :
        self.id: str = str(uuid.uuid4())
        self.name: str = name
        self.tone: str = tone
        self.isHuman: bool = isHuman
        self.isLocalPlayer: bool = isLocalPlayer
        self.role: Role = Role.CITIZEN

    def __str__(self) :
        return f'{self.name}[{"Human" if self.isHuman else "AI"}](role={self.role.name}, tone={self.tone})'

    def __repr__(self) :
        return f'{self.name}[{"Human" if self.isHuman else "AI"}](role={self.role.name}, tone={self.tone})'
