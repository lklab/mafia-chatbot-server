import random

from game.game_state import GameState
from game.player import *

def evaluateVoteStrategy(gameState: GameState, player: Player) :
    if player.info.role != Role.MAFIA :
        players = filter(lambda p : p != player, gameState.players)
    else :
        players = filter(lambda p : p.info.role != Role.MAFIA, gameState.players)

    players = list(players)
    target = random.choice(players).info
    strategy = Strategy([target], Role.CITIZEN)
    player.setStrategy(strategy)
