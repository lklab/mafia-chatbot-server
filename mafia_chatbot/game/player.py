from enum import Enum

class Role(Enum) :
    CITIZEN = 0
    MAFIA = 1
    POLICE = 2
    DOCTOR = 3

class Player :
    def __init__(self, name, isAI) :
        self.name = name
        self.isAI = isAI
        self.role = Role.CITIZEN

        self.publicRole = Role.CITIZEN
        self.currentTargets = []
        self.pastTargets = []
        self.strategy = None

    def __str__(self) :
        return self.name

    def __repr__(self) :
        return f'{self.name}({self.role.name})'
