import random

class Player :
    def __init__(self, id: int) :
        self.id: int = id
        self.positiveness: float = random.uniform(0.1, 1.0)
        self.discussionCount: int = 0

# setup dPlayers
temp: list[Player] = [Player(i) for i in range(10)]
weights: list[float] = list(map(lambda p: p.positiveness, temp))
players: list[Player] = []

while len(temp) > 0 :
    index: int = random.choices(range(len(temp)), weights=weights, k=1)[0]
    player: Player = temp[index]
    players.append(player)

    del temp[index]
    del weights[index]

# initialize variables
allDiscussionCount: int = 0

# discussion
for i in range(20) :
    player: Player = players[0]

    allDiscussionCount += 1
    player.discussionCount += 1
    players.remove(player)

    power: float = player.positiveness * allDiscussionCount / (player.discussionCount * (len(players) + 1))
    power = min(power, 1.0)
    if power > 1.0 :
        print(power)
    index: int = round(pow(random.random(), power) * len(players))
    players.insert(index, player)

# print results
print(', '.join(map(lambda p: f'p{p.id}({p.positiveness:.2f}): {p.discussionCount}', players)))
