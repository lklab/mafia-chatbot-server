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
        self.pastTargets = set()

    def __str__(self) :
        return self.name

    def __repr__(self) :
        return f'{self.name}({self.role.name})'

    def getDiscussion(self) :
        targetsStr = ', '.join(map(lambda p : p.name, self.currentTargets))
        return f'{self.name}: 저는 {targetsStr}를 의심합니다.'

if __name__ == "__main__" :
    p0 = Player('aa', True)
    p1 = Player('bb', True)
    p2 = Player('cc', True)

    p0.currentTargets.append(p1)
    p0.currentTargets.append(p2)
    print(p0.getDiscussion())
