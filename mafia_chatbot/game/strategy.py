from game.player_info import *

class Strategy :
    def __init__(self, targets: list[PlayerInfo], publicRole: Role = None) :
        self.targets = targets
        self.publicRole = publicRole
