from enum import Enum

class Role(Enum) :
    CITIZEN = 0
    MAFIA = 1
    POLICE = 2
    DOCTOR = 3

class PlayerInfo :
    def __init__(self, name: str, isAI: bool) :
        self.name: str = name
        self.isAI: bool = isAI
        self.role: Role = Role.CITIZEN

    def __str__(self) :
        return self.name

    def __repr__(self) :
        return f'{self.name}({self.role.name})'
