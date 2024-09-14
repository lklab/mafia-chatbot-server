import random
from typing import Callable

from game.game_state import GameState
from game.player import *

def pickOneStrategy(players: list[Player]) -> Strategy :
    target = random.choice(players).info
    return Strategy([target])

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

def evaluateVoteStrategyCitizen(gameState: GameState, player: Player) -> Strategy :
    strategy: Strategy = None

    # voting another player who targeted a citizen
    players: list[Player] = []
    for other in gameState.players :
        if other == player :
            continue

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

    # return
    return strategy

def evaluateVoteStrategyMafia(gameState: GameState, player: Player) -> Strategy :
    strategy: Strategy = None

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

    # return
    return strategy

def evaluateVoteStrategyPolice(gameState: GameState, player: Player) -> Strategy :
    knownMafias: list[Player] = []
    candidates: list[Player] = []

    for other in gameState.players :
        if other == player :
            continue

        if other in player.testResults :
            if player.testResults[other] == Role.MAFIA :
                knownMafias.append(other)
        else :
            candidates.append(other)

    # voting for a known mafia
    if len(knownMafias) > 0 :
        return pickOneStrategy(knownMafias)

    # voting another player who targeted a citizen
    players: list[Player] = []
    for other in candidates :
        for target in other.allTargets :
            targetPlayer = gameState.getPlayerByInfo(target)
            if not targetPlayer.isLive and target.role != Role.MAFIA :
                players.append(other)
                break

    if len(players) > 0 :
        return pickOneStrategy(players)

    # voting for a random target
    return pickOneStrategy(candidates)

voteStrategyEvaluator : dict[Role, Callable[[GameState, Player], None]] = {
    Role.CITIZEN: evaluateVoteStrategyCitizen,
    Role.MAFIA: evaluateVoteStrategyMafia,
    Role.POLICE: evaluateVoteStrategyPolice,
    Role.DOCTOR: evaluateVoteStrategyCitizen,
}

def evaluateVoteStrategy(gameState: GameState, player: Player) -> Strategy :
    return voteStrategyEvaluator[player.info.role](gameState, player)

def evaluateKillStrategy(gameState: GameState, mafia: Player) -> Strategy :
    # Kill the player who suspects me
    players: list[Player] = []
    for player in gameState.players :
        if player.info.role == Role.MAFIA :
            continue

        for target in player.allTargets :
            if target == mafia.info :
                players.append(player)
                break

    if len(players) > 0 :
        strategy: Strategy = pickOneStrategy(players)
        return strategy

    # Kill the player who suspects the other mafia
    players: list[Player] = []
    for player in gameState.players :
        if player.info.role == Role.MAFIA :
            continue

        for target in player.allTargets :
            if target.role == Role.MAFIA :
                players.append(player)
                break

    if len(players) > 0 :
        strategy: Strategy = pickOneStrategy(players)
        return strategy

    # Kill the random player
    players: list[Player] = list(filter(lambda p : p.info.role != Role.MAFIA, gameState.players))
    strategy: Strategy = pickOneStrategy(players)
    return strategy

def evaluateTestStrategy(gameState: GameState, police: Player) -> Strategy :
    candidates: list[Player] = list(filter(lambda p : p != police and p not in police.testResults, gameState.players))

    # test another player who targeted a citizen
    players: list[Player] = []
    for other in candidates :
        for target in other.allTargets :
            targetPlayer = gameState.getPlayerByInfo(target)
            if not targetPlayer.isLive and target.role != Role.MAFIA :
                players.append(other)
                break

    if len(players) > 0 :
        strategy: Strategy = pickOneStrategy(players)
        return strategy

    # test for a random target
    if len(candidates) > 0 :
        strategy: Strategy = pickOneStrategy(candidates)
        return strategy

    # already tested everyone
    strategy: Strategy = pickOneStrategy(gameState.players)
    return strategy

def evaluateHealStrategy(gameState: GameState, doctor: Player) -> Strategy :
    # Heal the player who suspects the mafia
    players: list[Player] = []
    for player in gameState.players :
        for target in player.allTargets :
            targetPlayer = gameState.getPlayerByInfo(target)
            if not targetPlayer.isLive and target.role == Role.MAFIA :
                players.append(player)
                break

    if len(players) > 0 :
        return pickOneStrategy(players)

    # Heal myself
    return Strategy([doctor.info])
