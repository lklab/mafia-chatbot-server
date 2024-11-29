import random
from typing import Callable

from mafia_chatbot.game.game_state import GameState, VoteData
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo, Role
from mafia_chatbot.game.strategy import Strategy, VoteStrategy, Assumption, Estimation
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.trust_profile import TrustProfile, normalizePoint
from mafia_chatbot.game.game_logger import GameLogger, FakeGameLogger

logger: GameLogger = FakeGameLogger()

def getOneTargetStrategy(publicRole: Role, targetInfo: PlayerInfo, reason: str) -> Strategy :
    return Strategy(publicRole, [Assumption([Estimation(targetInfo, Role.MAFIA)], reason)])

def evaluateDiscussionStrategy(gameState: GameState, recorder: TrustRecorder, me: Player) -> Strategy :
    if me.publicRole == Role.CITIZEN and me.info.role in _claimePoliceSelectors :
        assumption: Assumption = _claimePoliceSelectors[me.info.role](gameState, recorder, me)
        if assumption != None :
            return Strategy(Role.POLICE, [assumption])

    for selector in _targetSelecters :
        target, reason = selector(gameState, recorder, me)
        if target :
            logger.log(f'evaluateDiscussionStrategy result: publicRole={me.publicRole}, target={target.info.name}, reason={reason}')
            return getOneTargetStrategy(me.publicRole, target.info, reason)

def evaluateVoteStrategy(gameState: GameState, recorder: TrustRecorder, me: Player) -> VoteStrategy :
    for selector in _targetSelecters :
        target, _ = selector(gameState, recorder, me)
        if target :
            logger.log(f'evaluateVoteStrategy result: target={target.info.name}')
            return VoteStrategy(target.info)

def _getPolicePoiningMe(gameState: GameState, recorder: TrustRecorder, me: Player) -> tuple[Player, str] :
    for policeInfo in recorder.publicPolicePlayerInfos :
        police: Player = gameState.getPlayerByInfo(policeInfo)
        if me.info in police.estimationsAsPolice and police.estimationsAsPolice[me.info].role == Role.MAFIA :
            logger.log('apply method: _getPolicePoiningMe')
            return police, 'He pointed me of being the mafia, but I am not.'
    return None, None

def _getTargetFormTowPolice(gameState: GameState, recorder: TrustRecorder, me: Player) -> tuple[Player, str] :
    if len(recorder.publicPolicePlayerInfos) >= 2 :
        logger.log('apply method: _getTargetFormTowPolice')
        candidates: list[PlayerInfo] = []
        for policeInfo in recorder.publicPolicePlayerInfos :
            if policeInfo == me.info :
                continue
            candidates.append(policeInfo)
        logger.logCandidates(candidates)

        targetInfo: PlayerInfo = _choiceFromCandidates(gameState, recorder, me, candidates)
        targetPlayer: Player = gameState.getPlayerByInfo(targetInfo)
        return targetPlayer, recorder.getNegativeTrustReason(
            playerInfo=targetInfo,
            negativeReason='You claim that among those pretending to be the police, this person seems most like a mafia member.',
        )

    return None, None

def _getTargetConfirmedMafia(gameState: GameState, recorder: TrustRecorder, me: Player) -> tuple[Player, str] :
    candidates: list[PlayerInfo] = []
    for player in gameState.players :
        profile: TrustProfile = recorder.getTrustProfile(player.info)
        if profile.isMustTargeting() :
            candidates.append(player.info)

    if len(candidates) > 0 :
        logger.log('apply method: _getTargetConfirmedMafia')
        logger.logCandidates(candidates)

        targetInfo: PlayerInfo = _choiceFromCandidates(gameState, recorder, me, candidates)
        targetPlayer: Player = gameState.getPlayerByInfo(targetInfo)
        reason: str = recorder.getTrustReason(targetInfo)
        return targetPlayer, reason

    return None, None

def _getTargetFormTowDoctor(gameState: GameState, recorder: TrustRecorder, me: Player) -> tuple[Player, str] :
    if len(recorder.publicDoctorPlayerInfos) >= 2 :
        logger.log('apply method: _getTargetFormTowDoctor')
        candidates: list[PlayerInfo] = []
        for doctorInfo in recorder.publicDoctorPlayerInfos :
            if doctorInfo == me.info :
                continue
            candidates.append(doctorInfo)
        logger.logCandidates(candidates)

        targetInfo: PlayerInfo = _choiceFromCandidates(gameState, recorder, me, candidates)
        targetPlayer: Player = gameState.getPlayerByInfo(targetInfo)
        return targetPlayer, recorder.getNegativeTrustReason(
            playerInfo=targetInfo,
            negativeReason='You claim that among those pretending to be the doctor, this person seems most like a mafia member.',
        )

    return None, None

def _getTargetByTrustConformityRandom(gameState: GameState, recorder: TrustRecorder, me: Player) -> tuple[Player, str] :
    logger.log('apply method: _getTargetByTrustConformityRandom')

    candidates: list[PlayerInfo] = []
    for player in gameState.players :
        if player == me :
            continue
        candidates.append(player.info)
    logger.logCandidates(candidates)

    targetInfo: PlayerInfo = _choiceFromCandidates(gameState, recorder, me, candidates)
    targetPlayer: Player = gameState.getPlayerByInfo(targetInfo)
    return targetPlayer, recorder.getNegativeTrustReason(targetInfo)

_targetSelecters: list[Callable[[GameState, TrustRecorder, Player], tuple[Player, str]]] = [
    _getPolicePoiningMe,
    _getTargetFormTowPolice,
    _getTargetConfirmedMafia,
    _getTargetFormTowDoctor,
    _getTargetByTrustConformityRandom,
]

def _claimePoliceForPolice(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    pass

def _claimePoliceForMafia(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    # check state condition
    if (
        gameState.round > 0 and
        me.isFakePolice and
        (
            gameState.getMafiaCount() >= 2 or
            recorder.getEffectiveCitizenCount() <= 1
        ) and
        recorder.isPoliceLive and
        len(recorder.verifiedPoliceInfos) == 0 and
        len(list(filter(lambda info : info.role == Role.MAFIA, recorder.publicPolicePlayerInfos))) == 0
    ) :
        # check trigger conditions
        # 경찰 주장 플레이어가 없을 때 확률에 따라 경찰 주장
        if len(recorder.publicPolicePlayerInfos) == 0 and me.claimeFactor > random.random() :
            return _getTestResultsForMafia(gameState, recorder, me)

        myTrustPoint: float = recorder.getTrustPoint(me.info)
        for otherPublicPoliceInfo in recorder.publicPolicePlayerInfos :
            # 경찰 주장 플레이어의 신뢰도가 나보다 낮을 때 높은 확률로 경찰 주장
            if recorder.getTrustPoint(otherPublicPoliceInfo) < myTrustPoint and me.claimeFactor * 3.0 > random.random() :
                return _getTestResultsForMafia(gameState, recorder, me, mainTargetInfo=otherPublicPoliceInfo)

            # 경찰이 나를 시민 또는 마피아로 지목했을 때 경찰 주장
            otherPublicPolice: Player = gameState.getPlayerByInfo(otherPublicPoliceInfo)
            if me.info in otherPublicPolice.estimationsAsPolice :
                return _getTestResultsForMafia(gameState, recorder, me, mainTargetInfo=otherPublicPoliceInfo)

    return None

_claimePoliceSelectors: dict[Role, Callable[[GameState, TrustRecorder, Player], Assumption]] = {
    Role.POLICE : _claimePoliceForPolice,
    Role.MAFIA : _claimePoliceForMafia,
}

def _getTestResultsForMafia(gameState: GameState, recorder: TrustRecorder, me: Player, mainTargetInfo: PlayerInfo = None) -> Assumption :
    estimationCount: int = gameState.round

    ### 메인 타겟 정하기: 없는 경우 신뢰도 최저인 플레이어
    if mainTargetInfo == None :
        minPoint: float = 100.0
        for player in gameState.players :
            if player.info.role == Role.MAFIA :
                continue
            point: float = recorder.getTrustPoint(player.info)
            if point < minPoint :
                mainTargetInfo = player.info
                minPoint = point

    ### 결과를 공개할 플레이어 목록
    candidates: list[Player] = []
    for player in gameState.allPlayers :
        if player == me or player.info == mainTargetInfo :
            continue
        candidates.append(player)

    estimationTargets: list[Player] = []
    estimationTargets = random.sample(candidates, k=estimationCount-1)

    ### 역할 적용
    citizenCount: int = gameState.getCitizenCount()
    estimations: list[Estimation] = []

    # 메인 타겟에 마피아 역할 적용
    estimations.append(Estimation(mainTargetInfo, Role.MAFIA))

    for target in estimationTargets :
        # 탈락한 플레이어의 경우 실제 역할 적용
        if not target.isLive :
            estimations.append(Estimation(target.info, target.info.role))

        # 탈락하지 않은 플레이어의 경우 우선 시민 역할 적용
        elif citizenCount > 0 :
            estimations.append(Estimation(target.info, Role.CITIZEN))
            citizenCount -= 1

        # 시민 역할이 떨어진 경우 마피아 역할 적용
        else :
            estimations.append(Estimation(target.info, Role.MAFIA))

    ### 역할 지목 정리
    random.shuffle(estimations)
    estimations.sort(key=lambda estimation : estimation.role.value)
    return Assumption(
        estimations=estimations,
        reason='You investigated them.',
    )

def _choiceFromCandidates(gameState: GameState, recorder: TrustRecorder, me: Player, candidates: list[PlayerInfo]) -> PlayerInfo :
    n: int = len(candidates)
    if n <= 0 :
        return None
    if n == 1 :
        return candidates[0]

    weights: list[float] = []

    a: float = 0.95 # 다른 모든 플레이어의 신뢰도가 0일 때 신뢰도가 -100인 플레이어가 지목될 확률
    b: float = 0.99 # 다른 모든 플레이어가 해당 플레이어를 지목할 때 그 플레이어를 지목할 확률
    c: float = 0.5 # 0 ~ 1 사이의 값으로 이 값이 0에 가까울수록 더 적은 수의 플레이어가 지목했을 때 지목할 확률이 올라감

    d: float = 2.0 * a * n - 2.0
    e: float = 0.5 / (a * n - 1.0)
    f: float = 1.0 / n
    g: float = b - 1.0 / n
    h: float = 1.0 / (n - 1.0)

    myPointerOrVotersCount: int = len(recorder.getPointerOrVoters(me.info))
    isIFocused: bool = myPointerOrVotersCount >= round(gameState.getPlayerCount() / 2.5)

    for candidate in candidates :
        pointerOrVoters: set[PlayerInfo] = recorder.getPointerOrVoters(candidate)
        if me.info.role == Role.MAFIA and candidate.role == Role.MAFIA and len(pointerOrVoters) == 0 and not isIFocused :
            weights.append(0.0)
            continue

        # calculate weights using trust
        point: float = normalizePoint(recorder.getTrustPoint(candidate))
        tp: float = a / (d * (point + e)) # 다른 모든 플레이어의 신뢰도가 0일 때 현재 플레이어가 지목될 확률
        tw: float = (n - 1.0) * tp / (1.0 - tp)
        tw = pow(tw, me.trustSensitivity)

        # update weights using conformity
        sumOfPoint: float = 0.0
        for pointer in pointerOrVoters :
            sumOfPoint += normalizePoint(recorder.getTrustPoint(pointer)) * 2.0
        cp: float = f + g * pow(sumOfPoint * h, c)
        cp = min(cp, b)
        cw: float = (n - 1.0) * cp / (1.0 - cp)

        conformity: float = me.conformity
        if me.info.role == Role.MAFIA and candidate.role == Role.MAFIA :
            conformity *= 0.5

        cw = pow(cw, conformity)

        # apply weight
        weights.append(tw * cw)

    # choice
    return random.choices(candidates, weights=weights, k=1)[0]














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
            if estimate.playerInfo == None :
                continue
            elif estimate.playerInfo not in discussionTargets :
                discussionTargets[estimate.playerInfo] = [other]
            else :
                discussionTargets[estimate.playerInfo].append(other)

    conformityList: list[tuple[float, Player]] = []
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

        totalTrust = sum(map(lambda p: max(p.trustPoint + 100, 100), players))
        prob = ((50.0 - 0.5 * targetPlayer.trustPoint) / 100.0) * \
            (totalTrust / 100.0) * \
            conformity
        conformityList.append((prob, targetPlayer))

    conformityList.sort(key=lambda x : -x[0])

    for prob, targetPlayer in conformityList :
        if prob > random.random() :
            return targetPlayer, f'You agree with other players.'

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
    playerIndexes: list[int] = list(range(len(gameState.players)))
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
        targetPlayers: list[Player] = list(filter(lambda p : p.info.role != Role.MAFIA and p.trustPoint < TRUST_MAX, gameState.players))

    elif player.info.role == Role.POLICE : # for police
        targetPlayers: list[Player] = list(filter(
            lambda p :
                p != player and (
                    p not in player.testResults or player.testResults[p] == Role.MAFIA
                ) and
                p.trustPoint < TRUST_MAX,
            gameState.players
        ))

    else :
        targetPlayers: list[Player] = list(filter(lambda p : p != player and p.trustPoint < TRUST_MAX, gameState.players))

    target = random.choice(targetPlayers)
    reason: str = target.trustMainIssue
    if not reason :
        reason = 'Due to a lack of information, You will randomly suspect someone as the mafia.'
    return target, reason

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
    estimations.sort(key=lambda estimation : estimation.role.value)
    return estimations

def revealPoliceForMafia(gameState: GameState, player: Player) -> list[Estimation] :
    # check state condition
    if (
        gameState.round > 0 and
        player.isFakePolice and
        (gameState.getMafiaCount() >= 2 or gameState.getCitizenCount() <= 2) and
        gameState.isPoliceLive and
        len(list(filter(lambda p : p.isTrustedPolice, gameState.publicPolicePlayers))) == 0 and
        len(list(filter(lambda p : p.info.role == Role.MAFIA, gameState.publicPolicePlayers))) == 0
    ) :
        # check trigger condition
        if len(gameState.publicPolicePlayers) == 0 :
            prob: float = player.revealFactor
            if prob > random.random() :
                # reveal police
                return getTestResultsForMafia(gameState, player)

        for p in gameState.players :
            if p.info.role == Role.MAFIA or p.publicRole != Role.POLICE :
                continue

            if player.info in p.estimationsAsPolice and (
                p.estimationsAsPolice[player.info].role == Role.CITIZEN or
                p.trustPoint <= player.trustPoint
            ) :
                # reveal police
                return getTestResultsForMafia(gameState, player)

    return None

def getTestResultsForPolice(police: Player) -> list[Estimation] :
    estimations: list[Estimation] = []
    for p, role in police.testResults.items() :
        if role == Role.MAFIA :
            estimations.append(Estimation(p.info, Role.MAFIA))
        else :
            estimations.append(Estimation(p.info, Role.CITIZEN))

    random.shuffle(estimations)
    estimations.sort(key=lambda estimation : estimation.role.value)
    return estimations

def revealPoliceForPolice(gameState: GameState, player: Player) -> list[Estimation] :
    for p in gameState.publicPolicePlayers :
        if p not in player.testResults or player.testResults[p] != Role.CITIZEN :
            return getTestResultsForPolice(player)

    if len(player.testResults) == 0 :
        return None

    knownPlayerCount: int = len(list(filter(lambda p : p.isLive, player.testResults)))
    knownMafiaCount: int = len(list(filter(lambda p : player.testResults[p] == Role.MAFIA, player.testResults)))
    knownRatio: float = max(knownPlayerCount / gameState.getPlayerCount(), knownMafiaCount / gameState.getMafiaCount())
    revealProb: float = knownRatio * (1.0 - player.revealFactor) + player.revealFactor

    if revealProb > random.random() :
        return getTestResultsForPolice(player)

    return None

revealPoliceEvaluators: dict[Role, Callable[[GameState, Player], list[Estimation]]] = {
    Role.MAFIA : revealPoliceForMafia,
    Role.POLICE : revealPoliceForPolice,
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
    role: Role = player.testResults[target]
    if role != Role.MAFIA :
        role = Role.CITIZEN
    return Estimation(target.info, role)

updatePoliceTestEvaluators: dict[Role, Callable[[GameState, Player], Estimation]] = {
    Role.MAFIA : updatePoliceTestForMafia,
    Role.POLICE : updatePoliceTestForPolice,
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
            return VoteStrategy(target.info)

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
        if len(targets) > 0 :
            return random.choice(targets)

    return doctor
