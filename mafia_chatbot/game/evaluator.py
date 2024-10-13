import random
from typing import Callable

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.player import *

def getOneTargetStrategy(publicRole: Role, targetInfo: PlayerInfo, reason: str) -> Strategy :
    return Strategy(publicRole, [Assumption([Estimation(targetInfo, Role.MAFIA)], reason)])

def getMinTrustPlayer(players: list[Player], condition: Callable[[Player], bool]) -> Player :
    minPlayer: Player = None
    for player in players :
        if condition(player) and (minPlayer == None or player.trustPoint < minPlayer.trustPoint) :
            minPlayer = player
    return minPlayer

def getPolicePoiningMe(gameState: GameState, player: Player) -> tuple[Player, str] :
    for police in gameState.publicPolicePlayers :
        if player.info in police.estimationsAsPolice and police.estimationsAsPolice[player.info].role == Role.MAFIA :
            return police, 'He pointed me of being the mafia, but I am not.'
    return None, None

def getConformityTarget(gameState: GameState, player: Player) -> tuple[Player, str] :
    discussionTargets: dict[PlayerInfo, list[Player]] = {}
    for other in gameState.players :
        if other == player :
            continue

        if other.trustPoint == TRUST_MIN :
            continue

        strategy: Strategy = other.getVoteStrategy(gameState.round)
        if strategy == None :
            strategy: Strategy = other.getDiscussionStrategy(gameState.round)
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
        if targetPlayer == player or not targetPlayer.isLive :
            continue

        if player.info.role == Role.MAFIA and targetPlayer.info.role == Role.MAFIA :
            conformity: float = player.conformity * 0.5 # for mafia
        elif player.info.role == Role.POLICE and targetPlayer in player.testResults : # for police
            if player.testResults[targetPlayer] == Role.MAFIA :
                conformity: float = 10.0
            else :
                conformity: float = player.conformity * 0.5
        else :
            conformity: float = player.conformity

        totalTrust = sum(map(lambda p: max(p.trustPoint, 0), players))
        prob = ((50.0 - 0.5 * targetPlayer.trustPoint) / 100.0) * \
            ((100.0 + totalTrust) / 100.0) * \
            conformity
        conformityList.append((prob, target))

    conformityList.sort()

    for prob, target in conformityList :
        if prob > random.random() :
            conformityPlayer: Player = None
            for p in discussionTargets[target] :
                if conformityPlayer == None or p.trustPoint > conformityPlayer.trustPoint :
                    conformityPlayer = p

            return target, f'You agree with {conformityPlayer.info.name}\'s opinion.'

    return None, None

def getTargetFormTowPolice(gameState: GameState, player: Player) -> tuple[Player, str] :
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

            return targetPlayer, reason

    return None, None

def getTargetFromTestResults(_: GameState, player: Player) -> tuple[Player, str] :
    if player.info.role != Role.POLICE :
        return None, None

    target: Player = getMinTrustPlayer(list(player.testResults), lambda p : player.testResults[p] == Role.MAFIA)
    if target :
        reason: str = target.trustMainIssue
        if not reason :
            reason = 'Due to a lack of information, You will randomly suspect someone as the mafia.'
        return target, reason

    return None, None

def getTargetByTrust(gameState: GameState, player: Player) -> tuple[Player, str] :
    playerIndexes: list[int] = range(len(gameState.players))
    random.shuffle(playerIndexes)
    playerIndexes.sort(key=lambda i : gameState.players[i].trustPoint)

    for i in playerIndexes :
        other: Player = gameState.players[i]
        if other == player :
            continue

        # for mafia
        if player.info.role == Role.MAFIA and other.info.role == Role.MAFIA and other.trustPoint > TRUST_MIN :
            continue 
        # for police
        if player.info.role == Role.POLICE and other in player.testResults and player.testResults[other] == Role.CITIZEN :
            continue

        prob: float = -min(other.trustPoint, 0) / 100.0
        if prob > random.random() :
            reason: str = other.trustMainIssue
            if not reason :
                reason = 'Due to a lack of information, You will randomly suspect someone as the mafia.'
            return other, reason

    return None, None

def getRandomTarget(gameState: GameState, player: Player) -> tuple[Player, str] :
    if player.info.role == Role.MAFIA : # for mafia
        targetPlayers: list[Player] = list(filter(lambda p : p.info.role != Role.MAFIA, gameState.players))

    elif player.info.role == Role.POLICE : # for police
        targetPlayers: list[Player] = list(filter(
            lambda p :
                p != player and (
                    p not in player.testResults or player.testResults[p] == Role.MAFIA
                ),
            gameState.players
        ))

    else :
        targetPlayers: list[Player] = list(filter(lambda p : p != player, gameState.players))

    target = random.choice(targetPlayers)
    return target, 'Due to a lack of information, You will randomly suspect someone as the mafia.'

defaultEvaluators: list[Callable[[GameState, Player], tuple[Player, str]]] = [
    getPolicePoiningMe,
    getConformityTarget,
    getTargetFormTowPolice,
    getTargetFromTestResults,
    getTargetByTrust,
    getRandomTarget,
]

def getTestResultsForMafia(gameState: GameState, player: Player) -> list[Estimation] :
    estimations: list[Estimation] = []
    estimationCount: int = gameState.round
    mafiaCount: int = gameState.getMafiaCount()

    minTrustPlayer: Player = getMinTrustPlayer(
        list(gameState.publicPolicePlayers),
        lambda p : p != player and p.info.role != Role.MAFIA,
    )
    if not minTrustPlayer :
        minTrustPlayer: Player = getMinTrustPlayer(
            gameState.players,
            lambda p : p != player and p.info.role != Role.MAFIA,
        )
    if minTrustPlayer :
        estimations.append(Estimation(minTrustPlayer.info, Role.MAFIA))
        estimationCount -= 1
        mafiaCount -= 1

    estimationTargets = [p for p in gameState.allPlayers if p != minTrustPlayer and p != player]
    random.shuffle(estimationTargets)
    estimationTargets = estimationTargets[:estimationCount]

    for p in estimationTargets :
        if not p.isLive :
            if p.info.role == Role.MAFIA :
                estimations.append(Estimation(p.info, Role.MAFIA))
            else :
                estimations.append(Estimation(p.info, Role.CITIZEN))

    playerCount: int = gameState.gameInfo.playerCount - 1
    for p in estimationTargets :
        if p.isLive :
            if mafiaCount / max(playerCount - len(estimations), 1) > random.random() :
                estimations.append(Estimation(p.info, Role.MAFIA))
                mafiaCount -= 1
            else :
                estimations.append(Estimation(p.info, Role.CITIZEN))

    random.shuffle(estimations)
    estimations.sort(key=lambda estimation : estimation.role)
    return estimations

def revealPoliceForMafia(gameState: GameState, player: Player) -> list[Estimation] :
    # check state condition
    if (
        gameState.getMafiaCount() >= 2 and
        gameState.isPoliceLive and
        len(list(filter(lambda p : p.isTrustedPolice, gameState.publicPolicePlayers))) == 0 and
        len(list(filter(lambda p : p.info.role == Role.MAFIA, gameState.publicPolicePlayers))) == 0
    ) :
        # check trigger condition
        for p in gameState.players :
            if p.info.role == Role.MAFIA or p.publicRole != Role.POLICE :
                continue

            if (
                p.estimationsAsPolice[player.info].role == Role.CITIZEN or
                p.trustPoint < player.trustPoint
            ) :
                # reveal police
                return getTestResultsForMafia(gameState, player)

    return None

def getTestResultsForPolice(police: Player) -> list[Estimation] :
    estimations: list[Estimation] = []
    for p, role in police.testResults.items() :
        estimations.append(Estimation(p.info, role))

    random.shuffle(estimations)
    estimations.sort(key=lambda estimation : estimation.role)
    return estimations

def revealPoliceForPolice(gameState: GameState, player: Player) -> list[Estimation] :
    for p in gameState.publicPolicePlayers :
        if p not in player.testResults or player.testResults[p] != Role.CITIZEN :
            return getTestResultsForPolice(player)

    knownMafiaCount: int = len(list(filter(lambda p : player.testResults[p] == Role.MAFIA, player.testResults)))
    revealProb: float = (knownMafiaCount / gameState.getMafiaCount) * (1.0 - player.revealFactor) + player.revealFactor

    if revealProb > random.random() :
        return getTestResultsForPolice(player)

    return None

revealPoliceEvaluators: dict[Role, Callable[[GameState, Player], list[Estimation]]] = {
    { Role.MAFIA : revealPoliceForMafia },
    { Role.POLICE : revealPoliceForPolice },
}

def updatePoliceTestForMafia(gameState: GameState, player: Player) -> Estimation :
    estimatedMafiaCount: int = 0
    targets: list[Player] = []

    for p in gameState.players :
        if p == player :
            continue

        if p.info in player.estimationsAsPolice and player.estimationsAsPolice[p.info].role == Role.MAFIA :
            estimatedMafiaCount += 1
        elif p.info not in player.estimationsAsPolice :
            targets.append(p)

    target: Player = random.choice(targets)
    unknownMafia: int = gameState.getMafiaCount() - estimatedMafiaCount
    unknownPlayer: int = gameState.gameInfo.playerCount - len(player.estimationsAsPolice) - 1

    if unknownMafia / (max(unknownPlayer, 1)) > random.random() :
        return Estimation(target.info, Role.MAFIA)
    else :
        return Estimation(target.info, Role.CITIZEN)

def updatePoliceTestForPolice(_: GameState, player: Player) -> Estimation :
    target: Player = player.testedTargets[-1]
    return Estimation(target.info, player.testResults[target])

updatePoliceTestEvaluators: dict[Role, Callable[[GameState, Player], Estimation]] = {
    { Role.MAFIA : updatePoliceTestForMafia },
    { Role.POLICE : updatePoliceTestForPolice },
}

def evaluateDiscussionStrategy(gameState: GameState, player: Player) -> Strategy :
    if player.publicRole == Role.CITIZEN and player.info.role in revealPoliceEvaluators :
        estimations: list[Estimation] = revealPoliceEvaluators[player.info.role](gameState, player)
        if estimations != None :
            return Strategy(Role.POLICE, [Assumption(estimations, 'You investigated them.')])

    if player.publicRole == Role.POLICE and player.info.role in updatePoliceTestEvaluators :
        estimation: Estimation = updatePoliceTestEvaluators[player.info.role](gameState, player)
        if estimation != None :
            return Strategy(Role.POLICE, [Assumption([estimation], 'You investigated he.')])

    for evaluator in defaultEvaluators :
        target, reason = evaluator(gameState, player)
        if target :
            return getOneTargetStrategy(player.publicRole, target.info, reason)

def evaluateVoteStrategy(gameState: GameState, player: Player) -> VoteStrategy :
    for evaluator in defaultEvaluators :
        target, _ = evaluator(gameState, player)
        if target :
            return VoteStrategy(Estimation(target.info, Role.MAFIA))

def evaluateKillTarget(gameState: GameState) -> Player :
    if gameState.onePublicPolicePlayer != None and gameState.onePublicPolicePlayer.isLive and not gameState.isDoctorLive :
        return gameState.onePublicPolicePlayer

    targets: list[Player] = list(filter(lambda p : p.info.role != Role.MAFIA, gameState.players))
    return random.choice(targets)

def evaluateTestTarget(gameState: GameState, police: Player) -> Player :
    targets: list[Player] = []

    for player in gameState.players :
        if player != police and player not in police.testResults :
            targets.append(player)

    if len(targets) > 0 :
        targets.sort(key=lambda p : p.trustPoint)
        return random.choice(targets[:3])
    else :
        return None # all live player are known

def evaluateHealTarget(gameState: GameState, doctor: Player) -> Player :
    targets: list[Player] = list(filter(lambda p : p.trustPoint > TRUST_MIN, gameState.publicPolicePlayers))
    if len(targets) > 0 :
        return random.choice(targets)

    if doctor.selfHealFactor > random.random() :
        return doctor
    else :
        targets: list[Player] = list(filter(lambda p : p.trustPoint >= 0, gameState.players))
        return random.choice(targets)
