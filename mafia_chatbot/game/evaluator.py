import random
from typing import Callable

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo, Role
from mafia_chatbot.game.strategy import Strategy, VoteStrategy, Assumption, Estimation, AssumptionType
from mafia_chatbot.game.trust_recorder import TrustRecorder
from mafia_chatbot.game.trust_profile import TrustProfile, normalizePoint
from mafia_chatbot.game.game_logger import GameLogger, FakeGameLogger

logger: GameLogger = FakeGameLogger()

def getOneTargetStrategy(publicRole: Role, targetInfo: PlayerInfo, reason: str) -> Strategy :
    return Strategy(publicRole, [Assumption([Estimation(targetInfo, Role.MAFIA)], reason)])

# 토론 전략 생성
def evaluateDiscussionStrategy(gameState: GameState, recorder: TrustRecorder, me: Player) -> Strategy :
    if me.publicRole == Role.CITIZEN and me.info.role in _claimeSelectors :
        assumption: Assumption = _claimeSelectors[me.info.role](gameState, recorder, me)
        if assumption != None :
            logger.log(f'evaluateDiscussionStrategy result (claime): publicRole={me.publicRole}, assumption={assumption}')
            return Strategy(Role.POLICE, [assumption])

    if me.publicRole == Role.POLICE and me.info.role in _updateSelectors :
        assumption: Assumption = _updateSelectors[me.info.role](gameState, recorder, me)
        if assumption != None :
            logger.log(f'evaluateDiscussionStrategy result (update): publicRole={me.publicRole}, assumption={assumption}')
            return Strategy(Role.POLICE, [assumption])

    for selector in _targetSelecters :
        target, reason = selector(gameState, recorder, me)
        if target :
            logger.log(f'evaluateDiscussionStrategy result: publicRole={me.publicRole}, target={target.info.name}, reason={reason}')
            return getOneTargetStrategy(me.publicRole, target.info, reason)

# 투표 전략 생성
def evaluateVoteStrategy(gameState: GameState, recorder: TrustRecorder, me: Player) -> VoteStrategy :
    for selector in _targetSelecters :
        target, _ = selector(gameState, recorder, me)
        if target :
            logger.log(f'evaluateVoteStrategy result: target={target.info.name}')
            return VoteStrategy(target.info)

# 암살 전략
def evaluateKillTarget(gameState: GameState, recorder: TrustRecorder) -> Player :
    publicPolice: Player = None
    for playerInfo in recorder.publicPolicePlayerInfos :
        if playerInfo.role != Role.MAFIA :
            publicPolice = gameState.getPlayerByInfo(playerInfo)
            break

    publicDoctor: Player = None
    for playerInfo in recorder.publicDoctorPlayerInfos :
        if playerInfo.role != Role.MAFIA :
            publicDoctor = gameState.getPlayerByInfo(playerInfo)
            break

    # 생존하고 공개된 경찰이 있고 의사가 탈락한 경우
    if publicPolice != None and not recorder.isDoctorLive :
        logger.log(f'kill target (police): {publicPolice.info.name}')
        return publicPolice

    candidates: list[Player] = []
    weights: list[float] = []

    # 생존하고 공개된 경찰, 의사가 있을 경우
    if publicPolice != None and publicDoctor != None :
        logger.log(f'kill target (police or doctor or trust)')
        candidates.append(publicPolice)
        weights.append(1.0)
        candidates.append(publicDoctor)
        weights.append(1.0)

        maxPoint: float = -200.0
        maxPlayer: Player = None
        for p in gameState.players :
            if p == publicPolice or p == publicDoctor or p.info.role == Role.MAFIA :
                continue
            point: float = recorder.getTrustPoint(p.info)
            if point > maxPoint :
                maxPoint = point
                maxPlayer = p
        if maxPlayer != None :
            candidates.append(maxPlayer)
            weights.append(1.0)

    # 그 외의 경우 공개된 경찰/의사/마피아 제외하고 랜덤
    else :
        logger.log(f'kill target (except police and doctor)')
        for p in gameState.players :
            if p == publicPolice or p == publicDoctor or p.info.role == Role.MAFIA :
                continue
            point: float = recorder.getTrustPoint(p.info)
            candidates.append(p)
            weights.append(normalizePoint(point) + 0.01)

    logger.logCandidatesPlayerWithWeights(candidates, weights)
    target: Player = random.choices(candidates, weights=weights, k=1)[0]
    logger.log(f'kill target: {target.info.name}')
    return target

# 조사 전략
def evaluateTestTarget(gameState: GameState, recorder: TrustRecorder, police: Player) -> Player :
    candidates: list[Player] = []
    weights: list[float] = []

    for p in gameState.players :
        if p == police or p in police.testResults :
            continue
        point: float = recorder.getTrustPoint(p.info)
        candidates.append(p)
        weights.append(1.0 - normalizePoint(point) + 0.01)

    if len(candidates) > 0 :
        logger.logCandidatesPlayerWithWeights(candidates, weights)
        target: Player = random.choices(candidates, weights=weights, k=1)[0]
        logger.log(f'test target: {target.info.name}')
        return target
    else :
        logger.log(f'no test target')
        return None # all live player are known

# 치료 전략
def evaluateHealTarget(gameState: GameState, recorder: TrustRecorder, doctor: Player) -> Player :
    if recorder.onePublicPolicePlayerInfo != None :
        police: Player = gameState.getPlayerByInfo(recorder.onePublicPolicePlayerInfo)
        # 공개된 경찰이 있고 자신은 공개되지 않은 경우
        if doctor.publicRole == Role.CITIZEN :
            mainTargets = [police]
        # 공개된 경찰이 있고 자신도 공개된 경우
        else :
            mainTargets = [doctor, police]
    # 공개된 경찰이 없을 경우
    else :
        mainTargets = [doctor]

    if doctor.mainHealFactor > random.random() :
        logger.logCandidatesPlayer(mainTargets)
        target: Player = random.choice(mainTargets)
        logger.log(f'heal target (main): {target.info.name}')
        return target

    else :
        candidates: list[Player] = []
        weights: list[float] = []

        for p in gameState.players :
            point: float = recorder.getTrustPoint(p.info)
            if point >= 0.0 :
                candidates.append(p)
                weights.append(normalizePoint(point))

        if len(candidates) > 0 :
            logger.logCandidatesPlayerWithWeights(candidates, weights)
            target: Player = random.choices(candidates, weights=weights, k=1)[0]
            logger.log(f'heal target (sub): {target.info.name}')
            return target
        else :
            logger.log(f'heal target (self)')
            return doctor

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
        profile: TrustProfile = recorder.getTrustProfile(player.info)
        if player == me or not profile.isTargetable() :
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
    # 시민으로 조사되지 않은 플레이어가 경찰 주장을 한 경우
    for p in recorder.publicPolicePlayerInfos :
        if p not in me.testResults or me.testResults[p] != Role.CITIZEN :
            logger.log('claime police: counter')
            return _getTestResultsForPolice(gameState, recorder, me)

    # 조사한 정보가 없으면 공개하지 않음
    if len(me.testResults) == 0 :
        return None

    # 조사율과 공개확률에 따라 공개
    knownMafiaCount: int = len(list(filter(lambda p : p.isLive, me.testedMafias)))
    knownCitizenCount: int = len(list(filter(lambda p : p.isLive, me.testedCitizens)))
    knownRatio: float = max(knownMafiaCount / gameState.getMafiaCount(), knownCitizenCount / gameState.getCitizenCount())
    logger.log(f'claime police: knownRatio={knownRatio}')
    if knownRatio * me.claimeFactor > random.random() :
        logger.log('claime police: random')
        return _getTestResultsForPolice(gameState, recorder, me)

    return None

def _getTestResultsForPolice(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    estimations: list[Estimation] = []
    for p, role in me.testResults.items() :
        estimations.append(Estimation(
            playerInfo=p.info,
            role=Role.MAFIA if role == Role.MAFIA else Role.CITIZEN,
        ))

    random.shuffle(estimations)
    estimations.sort(key=lambda estimation : estimation.role.value)
    return Assumption(
        estimations=estimations,
        reason='You investigated them.',
        assumptionType=AssumptionType.TEST_RESULT,
    )

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
            logger.log('claime police: random')
            return _getTestResultsForMafia(gameState, recorder, me)

        myTrustPoint: float = recorder.getTrustPoint(me.info)
        for otherPublicPoliceInfo in recorder.publicPolicePlayerInfos :
            # 경찰 주장 플레이어의 신뢰도가 나보다 낮을 때 높은 확률로 경찰 주장
            if recorder.getTrustPoint(otherPublicPoliceInfo) < myTrustPoint and me.claimeFactor * 3.0 > random.random() :
                logger.log('claime police: trust')
                return _getTestResultsForMafia(gameState, recorder, me, mainTargetInfo=otherPublicPoliceInfo)

            # 경찰이 나를 시민 또는 마피아로 지목했을 때 경찰 주장
            otherPublicPolice: Player = gameState.getPlayerByInfo(otherPublicPoliceInfo)
            if me.info in otherPublicPolice.estimationsAsPolice :
                logger.log('claime police: I\'m targeted')
                return _getTestResultsForMafia(gameState, recorder, me, mainTargetInfo=otherPublicPoliceInfo)

    return None

def _getTestResultsForMafia(gameState: GameState, recorder: TrustRecorder, me: Player, mainTargetInfo: PlayerInfo = None) -> Assumption :
    estimationCount: int = gameState.round

    ### 메인 타겟 정하기: 없는 경우 신뢰도 최저인 플레이어
    if mainTargetInfo == None :
        minPoint: float = 200.0
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
    logger.logCandidatesPlayer(candidates)

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
            estimations.append(Estimation(target.info, Role.MAFIA if target.info.role == Role.MAFIA else Role.CITIZEN))

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
        assumptionType=AssumptionType.TEST_RESULT,
    )

def _claimeDoctorForDoctor(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    # 치료에 성공한 내역이 없으면 의사 주장을 하지 않음
    if len(me.healSuccesses) == 0 :
        return None

    # 자신이 치료에 성공한 플레이어가 마피아로 몰린 경우
    playerCount = gameState.getPlayerCount()
    for player in gameState.players :
        if player in me.healSuccesses :
            count: int = len(recorder.getPointerOrVoters(player.info))
            if (count * 2.0 / playerCount) * me.claimeFactor > random.random() :
                logger.log('claime doctor: random')
                return _getHealSuccessesForDoctor(gameState, recorder, me)

    # 다른 플레이어가 의사 주장을 한 경우
    for p in recorder.publicDoctorPlayerInfos :
        if p not in me.healSuccesses :
            logger.log('claime doctor: counter')
            return _getHealSuccessesForDoctor(gameState, recorder, me)

    return None

def _getHealSuccessesForDoctor(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    estimations: list[Estimation] = []
    for p in me.healSuccesses :
        estimations.append(Estimation(
            playerInfo=p.info,
            role=Role.CITIZEN,
        ))

    random.shuffle(estimations)
    return Assumption(
        estimations=estimations,
        reason='Since you successfully treated that player, they are a civilian.',
        assumptionType=AssumptionType.HEAL_SUCCESS,
    )

_claimeSelectors: dict[Role, Callable[[GameState, TrustRecorder, Player], Assumption]] = {
    Role.POLICE : _claimePoliceForPolice,
    Role.MAFIA : _claimePoliceForMafia,
    Role.DOCTOR: _claimeDoctorForDoctor,
}

def _updatePoliceForPolice(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    if me.lastTestedTarget != None :
        role: Role = Role.MAFIA if me.testResults[me.lastTestedTarget] == Role.MAFIA else Role.CITIZEN
        return Assumption(
            estimations=[Estimation(me.lastTestedTarget.info, role)],
            reason='You investigated them.',
            assumptionType=AssumptionType.TEST_RESULT,
        )

    return None

def _updatePoliceForMafia(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    logger.log('apply method: _updatePoliceForMafia')
    citizenCount: int = gameState.getCitizenCount()

    for estimation in me.estimationsAsPolice.values() :
        target: Player = gameState.getPlayerByInfo(estimation.playerInfo)
        if target.isLive and estimation.role == Role.CITIZEN :
            citizenCount -= 1

    candidates: list[PlayerInfo] = []
    for player in gameState.players :
        if player == me or player in me.estimationsAsPolice :
            continue
        candidates.append(player.info)
    logger.logCandidates(candidates)

    if len(candidates) == 0 :
        return None

    targetInfo: PlayerInfo = random.choice(candidates)
    role: Role = Role.CITIZEN if citizenCount > 0 else Role.MAFIA

    return Assumption(
        estimations=[Estimation(targetInfo, role)],
        reason='You investigated them.',
        assumptionType=AssumptionType.TEST_RESULT,
    )

def _updateDoctorForDoctor(gameState: GameState, recorder: TrustRecorder, me: Player) -> Assumption :
    if me.lastHealSuccess != None :
        return Assumption(
            estimations=[Estimation(me.lastHealSuccess.info, Role.CITIZEN)],
            reason='Since you successfully treated that player, they are a civilian.',
            assumptionType=AssumptionType.HEAL_SUCCESS,
        )

    return None

_updateSelectors: dict[Role, Callable[[GameState, TrustRecorder, Player], Assumption]] = {
    Role.POLICE : _updatePoliceForPolice,
    Role.MAFIA : _updatePoliceForMafia,
    Role.DOCTOR : _updateDoctorForDoctor,
}

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

        # 마피아일 경우 아무도 지목하지 않은 마피아 동료를 지목하지 않음
        if me.info.role == Role.MAFIA and candidate.role == Role.MAFIA and len(pointerOrVoters) == 0 and not isIFocused :
            weights.append(0.0)
            continue

        # 경찰일 경우 조사된 마피아가 있다면 아무도 지목하지 않은 조사되지 않거나 시민으로 조사된 플레이어를 지목하지 않음
        if me.info.role == Role.POLICE and len(pointerOrVoters) == 0 and len(list(filter(lambda p : p.isLive, me.testedMafias))) > 0 :
            p: Player = gameState.getPlayerByInfo(candidate)
            if p not in me.testResults or me.testResults[p] != Role.MAFIA :
                weights.append(0.0)
                continue

        # 의사일 경우 아무도 지목하지 않은, 치료에 성공한 플레이어를 지목하지 않음
        if me.info.role == Role.DOCTOR and len(pointerOrVoters) == 0 :
            p: Player = gameState.getPlayerByInfo(candidate)
            if p in me.healSuccesses :
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

        # 마피아일 경우 동료 마피아에 대해 낮은 동조
        if me.info.role == Role.MAFIA and candidate.role == Role.MAFIA :
            conformity *= 0.5

        # 경찰일 경우 조사한 시민, 마피아에 대해 동조값 변경
        if me.info.role == Role.POLICE :
            p: Player = gameState.getPlayerByInfo(candidate)
            if p in me.testResults :
                if me.testResults[p] == Role.MAFIA :
                    conformity *= 10.0
                else :
                    conformity *= 0.5

        # 의사일 경우 치료에 성공한 플레이어에 대해 동조값 변경
        if me.info.role == Role.DOCTOR :
            p: Player = gameState.getPlayerByInfo(candidate)
            if p in me.healSuccesses :
                conformity *= 0.5

        cw = pow(cw, conformity)

        # apply weight
        weights.append(tw * cw)

    # choice
    logger.logCandidatesWithWeights(candidates, weights)
    return random.choices(candidates, weights=weights, k=1)[0]
