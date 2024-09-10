import random
from typing import Callable

from game.game_state import GameState
from game.player import *

def pickOneStrategy(players: list[Player], publicRole=Role.CITIZEN) -> Strategy :
    target = random.choice(players).info
    return Strategy([target], publicRole)

def sameTargetStrategy(gameState: GameState, player: Player) -> Strategy :
    if player.strategy == None :
        return None

    targets: list[PlayerInfo] = []

    for target in player.strategy.targets :
        targetPlayer = gameState.getPlayerByInfo(target)
        if targetPlayer.isLive :
            targets.append(target)

    if len(targets) == 0 :
        return None

    return Strategy(targets)

def evaluateVoteStrategyCitizen(gameState: GameState, player: Player) :
    strategy = None

    # voting another player who targeted a citizen
    players: list[Player] = []
    for other in gameState.players :
        if other != player :
            for target in other.allTargets :
                targetPlayer = gameState.getPlayerByInfo(target)
                if not targetPlayer.isLive and target.role != Role.MAFIA :
                    players.append(other)
                    break

    if len(players) > 0 :
        strategy = pickOneStrategy(players)

    # voting for a random target
    if strategy == None :
        players = list(filter(lambda p : p != player, gameState.players))
        strategy = pickOneStrategy(players)

    # set strategy
    player.setStrategy(strategy)

def evaluateVoteStrategyMafia(gameState: GameState, player: Player) :
    strategy = None

    # voting for the same target as another mafia member
    for mafia in gameState.mafiaPlayers :
        if mafia != player :
            strategy = sameTargetStrategy(gameState, mafia)
            if strategy != None :
                break

    # voting for a random target
    if strategy == None :
        players = list(filter(lambda p : p.info.role != Role.MAFIA, gameState.players))
        strategy = pickOneStrategy(players)

    # set strategy
    player.setStrategy(strategy)

voteStrategyEvaluator : dict[Role, Callable[[GameState, Player], None]] = {
    Role.CITIZEN: evaluateVoteStrategyCitizen,
    Role.MAFIA: evaluateVoteStrategyMafia,
    Role.POLICE: evaluateVoteStrategyCitizen,
    Role.DOCTOR: evaluateVoteStrategyCitizen,
}

def evaluateVoteStrategy(gameState: GameState, player: Player) :
    voteStrategyEvaluator[player.info.role](gameState, player)
