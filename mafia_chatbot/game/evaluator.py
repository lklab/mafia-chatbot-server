import random
from typing import Callable

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.player import *

def getOneTargetStrategy(publicRole: Role, targetInfo: PlayerInfo, reason: str) -> Strategy :
    return Strategy(publicRole, [Assumption([Estimation(targetInfo, Role.MAFIA)], reason)])

def evaluateDiscussionStrategy(gameState: GameState, player: Player) -> Strategy :
    # the police who pointed me of being the mafia
    for police in gameState.publicPolicePlayers :
        if player.info in police.estimationsAsPolice and police.estimationsAsPolice[player.info].role == Role.MAFIA :
            return getOneTargetStrategy(player.publicRole, police.info, 'He pointed me of being the mafia, but I am not.')

    # conformity
    discussionTargets: dict[PlayerInfo, list[Player]] = {}
    for other in gameState.players :
        if other == player :
            continue

        if other.trustPoint == TRUST_MIN :
            continue

        strategy: Strategy = other.discussionStrategy
        if strategy == None :
            continue

        for estimate in strategy.mafiaEstimations :
            if estimate.playerInfo not in discussionTargets :
                discussionTargets[estimate.playerInfo] = [other]
            else :
                discussionTargets[estimate.playerInfo].append(other)

    conformityList: list[tuple[float, PlayerInfo]] = []
    for target, players in discussionTargets.items() :
        targetPlayer: Player = gameState.getPlayerByInfo(target)
        if targetPlayer == player :
            continue

        totalTrust = sum(map(lambda p: max(p.trustPoint, 0), players))
        prob = ((50.0 - 0.5 * targetPlayer.trustPoint) / 100.0) * \
            ((100.0 + totalTrust) / 100.0) * \
            player.conformity
        conformityList.append((prob, target))

    conformityList.sort()

    for prob, target in conformityList :
        if prob > random.random() :
            conformityPlayer: Player = None
            for p in discussionTargets[target] :
                if conformityPlayer == None or p.trustPoint > conformityPlayer.trustPoint :
                    conformityPlayer = p

            return getOneTargetStrategy(player.publicRole, target, f'You agree with {conformityPlayer.info.name}\'s opinion.')

    # two polices
    if len(gameState.publicPolicePlayers) >= 2 :
        targetPlayers: list[Player] = []
        for police in gameState.publicPolicePlayers :
            if police == player :
                continue

            if not targetPlayers or police.trustPoint == targetPlayers[0].trustPoint :
                targetPlayers.append(police)
            elif police.trustPoint < targetPlayers[0].trustPoint :
                targetPlayers.clear()
                targetPlayers.append(police)

        if targetPlayers :
            targetPlayer: Player = random.choice(targetPlayers)

            reason: str = targetPlayer.trustMainIssue
            if not reason :
                if player.publicRole == Role.POLICE :
                    reason = 'Your role is the police.'
                else :
                    reason = 'He seems a bit more suspicious.'

            return getOneTargetStrategy(player.publicRole, targetPlayer.info, reason)

    # trust point
    playerIndexes: list[int] = range(len(gameState.players))
    random.shuffle(playerIndexes)
    playerIndexes.sort(key=lambda i : gameState.players[i].trustPoint)

    for i in playerIndexes :
        other: Player = gameState.players[i]
        if other == player :
            continue

        prob: float = -min(other.trustPoint, 0) / 100.0
        if prob > random.random() :
            reason: str = other.trustMainIssue
            if not reason :
                reason = 'Due to a lack of information, You will randomly suspect someone as the mafia.'
            return getOneTargetStrategy(player.publicRole, other.info, reason)

    # random player
    targetPlayers: list[Player] = list(filter(lambda p : p != player, gameState.players))
    target = random.choice(targetPlayers)
    return getOneTargetStrategy(
        player.publicRole,
        target.info,
        'Due to a lack of information, You will randomly suspect someone as the mafia.'
    )

def pickOne(players: list[Player]) -> PlayerInfo :
    return random.choice(players).info

def pickOneStrategy(players: list[Player], publicRole: Role = None, reason: str = '') -> Strategy :
    target = pickOne(players)
    return Strategy([(target, Role.MAFIA)], publicRole, reason)

def sameTargetStrategy(gameState: GameState, player: Player, publicRole: Role = None, reason: str = '') -> Strategy :
    if player.strategy == None :
        return None

    assumptions: list[tuple[PlayerInfo, Role]] = []

    for playerInfo, role in player.strategy.assumptions :
        player: Player = gameState.getPlayerByInfo(playerInfo)
        if player.isLive :
            assumptions.append((playerInfo, role))

    if len(assumptions) == 0 :
        return None

    return Strategy(assumptions, publicRole, reason)

def evaluateDiscussionStrategyCitizen(gameState: GameState, player: Player) -> Strategy :
    # targeting another player who targeted a citizen
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
        return pickOneStrategy(
            players,
            reason='You suspect him of being a mafia because he previously suspected a citizen of being a mafia.',
        )

    # targeting for a random player
    players = list(filter(lambda p : p != player, gameState.players))
    return pickOneStrategy(
        players,
        reason='Due to a lack of information, You will randomly suspect someone as the mafia.',
    )

def evaluateDiscussionStrategyMafia(gameState: GameState, player: Player) -> Strategy :
    # targeting for the same target as another mafia member
    for mafia in gameState.mafiaPlayers :
        if mafia != player :
            strategy: Strategy = sameTargetStrategy(
                gameState,
                mafia,
                reason=f'You suspect him as the mafia because you agree with {mafia.info.name}\'s opinion.',
            )
            if strategy != None :
                return strategy

    # targeting for a random target
    players = list(filter(lambda p : p.info.role != Role.MAFIA, gameState.players))
    return pickOneStrategy(
        players,
        reason='Due to a lack of information, You will randomly suspect someone as the mafia.',
    )

def evaluateDiscussionStrategyPolice(gameState: GameState, player: Player) -> Strategy :
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

    # targeting for a known mafia
    if len(knownMafias) > 0 :
        return pickOneStrategy(
            knownMafias,
            publicRole=Role.POLICE,
            reason='You know he is the mafia because your role is police.',
        )

    # targeting another player who targeted a citizen
    players: list[Player] = []
    for other in candidates :
        for target in other.allTargets :
            targetPlayer = gameState.getPlayerByInfo(target)
            if not targetPlayer.isLive and target.role != Role.MAFIA :
                players.append(other)
                break

    if len(players) > 0 :
        return pickOneStrategy(
            players,
            reason='You suspect him of being a mafia because he previously suspected a citizen of being a mafia.',
        )

    # targeting for a random target
    return pickOneStrategy(
        candidates,
        reason='Due to a lack of information, You will randomly suspect someone as the mafia.',
    )

discussionStrategyEvaluator : dict[Role, Callable[[GameState, Player], None]] = {
    Role.CITIZEN: evaluateDiscussionStrategyCitizen,
    Role.MAFIA: evaluateDiscussionStrategyMafia,
    Role.POLICE: evaluateDiscussionStrategyPolice,
    Role.DOCTOR: evaluateDiscussionStrategyCitizen,
}

def evaluateDiscussionStrategy(gameState: GameState, player: Player) -> Strategy :
    return discussionStrategyEvaluator[player.info.role](gameState, player)

def evaluateVoteTarget(gameState: GameState, player: Player) -> Strategy :
    strategy: Strategy = evaluateDiscussionStrategy(gameState, player)
    return strategy.mainTarget

def evaluateKillTarget(gameState: GameState, mafia: Player) -> PlayerInfo :
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
        return pickOne(players)

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
        return pickOne(players)

    # Kill the random player
    players: list[Player] = list(filter(lambda p : p.info.role != Role.MAFIA, gameState.players))
    return pickOne(players)

def evaluateTestTarget(gameState: GameState, police: Player) -> PlayerInfo :
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
        return pickOne(players)

    # test for a random target
    if len(candidates) > 0 :
        return pickOne(players)

    # already tested everyone
    return pickOne(players)

def evaluateHealTarget(gameState: GameState, doctor: Player) -> PlayerInfo :
    # Heal the player who suspects the mafia
    players: list[Player] = []
    for player in gameState.players :
        for target in player.allTargets :
            targetPlayer = gameState.getPlayerByInfo(target)
            if not targetPlayer.isLive and target.role == Role.MAFIA :
                players.append(player)
                break

    if len(players) > 0 :
        return pickOne(players)

    # Heal myself
    return doctor.info
