import random

from game.game_state import GameState
from game.player import *

def evaluateVoteStrategy(gameState: GameState, player: Player) :
    if player.role != Role.MAFIA :
        players = filter(lambda p : p != player, gameState.players)
    else :
        players = filter(lambda p : p.role != Role.MAFIA, gameState.players)

    players = list(players)
    player.pastTargets |= set(player.currentTargets)
    player.currentTargets.clear()
    player.currentTargets.append(random.choice(players))
