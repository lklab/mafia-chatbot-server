from mafia_chatbot.game.game_state import GameState, VoteData, RemoveReason
from mafia_chatbot.game.trust_profile import TrustProfile, TrustRecord, TrustState, defaultReason
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo, Role
from mafia_chatbot.game.strategy import Strategy, VoteStrategy

class TrustRecorder :
    def __init__(self, gameState: GameState) :
        self.gameState = gameState

        # profile
        self.profileByPlayerInfo: dict[PlayerInfo, TrustProfile]
        for player in gameState.players :
            profile: TrustProfile = TrustProfile()
            self.profileByPlayerInfo[player.info] = profile

        # police
        self.isPoliceLive = True
        self.publicPolicePlayerInfos: set[PlayerInfo] = set()
        self.onePublicPolicePlayerInfo: PlayerInfo = None
        self.verifiedPoliceInfos: set[PlayerInfo] = set()

        # doctor
        self.isDoctorLive = True
        self.publicDoctorPlayerInfos: set[PlayerInfo] = set()
        self.onePublicDoctorPlayerInfo: PlayerInfo = None
        self.healSucceededList: list[PlayerInfo] = []

        # etc data
        self.pointedTrustedTarget: list[tuple[PlayerInfo, PlayerInfo]] = [] # tuple[pointer, target]

    def startNewRound(self) :
        # 특정 플레이어를 지목한 플레이어 리스트: 지목한 적이 있으면 나중에 번복해도 계속 쌓임
        self.everPointerInfosByTargetInfo: dict[PlayerInfo, list[PlayerInfo]] = {}
        self.everPointerInfoSetByTargetInfo: dict[PlayerInfo, set[PlayerInfo]] = {}

        # 특정 플레이어를 지목하거나 투표한 플레이어 리스트: 가장 최근에 지목하거나 투표한 것만 반영됨
        self.pointerOrVoterInfosByTargetInfo: dict[PlayerInfo, set[PlayerInfo]] = {}
        self.targetInfoByPointerOrVoterInfo: dict[PlayerInfo, PlayerInfo] = {}

        # 누군가를 지목한 적이 있는 플레이어
        self.everPointerPlayerInfos: set[PlayerInfo] = set()

        # 마피아 플레이어가 지목한 플레이어와 그 당시의 상황을 반영한 지목당한 플레이어의 신뢰도 값
        self.mafiaPointingData: dict[PlayerInfo, dict[PlayerInfo, float]] = {}

    def discussionStrategyUpdated(self, playerInfo: PlayerInfo, strategy: Strategy) :
        player: Player = self.gameState.getPlayerByInfo(playerInfo)

        # update police
        if player.publicRole == Role.POLICE :
            self.publicPolicePlayerInfos.add(playerInfo)
        self._updateOnePublicPolicePlayerInfo()

        # update doctor
        if player.publicRole == Role.DOCTOR :
            self.publicDoctorPlayerInfos.add(playerInfo)
        self._updateOnePublicDoctorPlayerInfo()

        for estimation in strategy.mafiaEstimations :
            targetInfo: PlayerInfo = estimation.playerInfo

            # update everPointerInfosByTargetInfo
            if targetInfo not in self.everPointerInfosByTargetInfo :
                self.everPointerInfosByTargetInfo[targetInfo] = []
                self.everPointerInfoSetByTargetInfo[targetInfo] = set()

            if playerInfo not in self.everPointerInfosByTargetInfo[targetInfo] :
                self.everPointerInfosByTargetInfo[targetInfo].append(playerInfo)
                self.everPointerInfoSetByTargetInfo[targetInfo].add(playerInfo)

            # update pointedTrustedTarget
            # 현재 신뢰받는 상태인 플레이어를 지목한 경우 신뢰도를 낮게 설정하는데,
            # 나중에 해당 플레이어가 신뢰 상태가 아닐 수 있으므로
            # _checkAndUpdateTrustStateStep2()에서 타겟의 신뢰 상태를 다시 검사함
            targetProfile: TrustProfile = self.profileByPlayerInfo[targetInfo]
            if not targetProfile.isTargetable() :
                self.pointedTrustedTarget.append((playerInfo, targetInfo))

            # update pointerOrVoterInfosByTargetInfo
            beforeTargetInfo: PlayerInfo = self.targetInfoByPointerOrVoterInfo.get(playerInfo)
            if beforeTargetInfo != None :
                self.pointerOrVoterInfosByTargetInfo[beforeTargetInfo].discard(playerInfo)

            if targetInfo not in self.pointerOrVoterInfosByTargetInfo :
                self.pointerOrVoterInfosByTargetInfo[targetInfo] = set()

            self.pointerOrVoterInfosByTargetInfo[targetInfo].add(playerInfo)
            self.targetInfoByPointerOrVoterInfo[playerInfo] = targetInfo

        # update mafiaPointingData
        self.everPointerPlayerInfos.add(playerInfo)
        if playerInfo.role == Role.MAFIA :
            if playerInfo not in self.mafiaPointingData :
                self.mafiaPointingData[playerInfo] = {}

            basePoint: float = 100.0 / (len(self.everPointerPlayerInfos) * (self.gameState.getMafiaCount() - 1))

            for estimation in strategy.mafiaEstimations :
                targetInfo: PlayerInfo = estimation.playerInfo
                point: float = basePoint * (self.getTrustPoint(targetInfo) + 100) / 200.0
                point = min(point, 80.0)
                self.mafiaPointingData[playerInfo][targetInfo] = point

    def voteStrategyUpdated(self, playerInfo: PlayerInfo, strategy: VoteStrategy) :
        for estimation in strategy.mafiaEstimations :
            targetInfo: PlayerInfo = estimation.playerInfo

            # update pointerOrVoterInfosByTargetInfo
            beforeTargetInfo: PlayerInfo = self.targetInfoByPointerOrVoterInfo.get(playerInfo)
            if beforeTargetInfo != None :
                self.pointerOrVoterInfosByTargetInfo[beforeTargetInfo].discard(playerInfo)

            if targetInfo not in self.pointerOrVoterInfosByTargetInfo :
                self.pointerOrVoterInfosByTargetInfo[targetInfo] = set()

            self.pointerOrVoterInfosByTargetInfo[targetInfo].add(playerInfo)
            self.targetInfoByPointerOrVoterInfo[playerInfo] = targetInfo

    def playerRemoved(self, removedPlayerInfo: PlayerInfo, removeReason: RemoveReason) :
        self._updateTrustRecordsByPlayerRemoved(removedPlayerInfo, removeReason)

        # police
        if removedPlayerInfo.role == Role.POLICE :
            self.isPoliceLive = False
        self.publicPolicePlayerInfos.discard(removedPlayerInfo)
        self.verifiedPoliceInfos.discard(removedPlayerInfo)
        self._updateOnePublicPolicePlayerInfo()

        if removedPlayerInfo.role == Role.MAFIA :
            for policeInfo in self.publicPolicePlayerInfos :
                policePlayer: Player = self.gameState.getPlayerByInfo(policeInfo)
                for estimation in policePlayer.estimationsAsPolice.values() :
                    if estimation.role == Role.MAFIA and estimation.playerInfo == removedPlayerInfo :
                        self.verifiedPoliceInfos.add(policeInfo)
                        break

        # doctor
        if removedPlayerInfo.role == Role.DOCTOR :
            self.isDoctorLive = False
        self.publicDoctorPlayerInfos.discard(removedPlayerInfo)
        self._updateOnePublicDoctorPlayerInfo()

    def healSucceeded(self, target: PlayerInfo) :
        self.healSucceededList.append(target)

    def updateTrustRecords(self) :
        playerCount: int = len(self.gameState.players)

        for i in range(playerCount) :
            player: Player = self.gameState.players[i]
            profile: TrustProfile = self.profileByPlayerInfo[player.info]
            self._checkAndUpdateTrustStateStep1(player, profile)

        self._checkAndUpdateTrustStateStep2()

    def getTrustProfile(self, playerInfo: PlayerInfo) -> TrustProfile :
        return self.profileByPlayerInfo[playerInfo]

    def getTrustPoint(self, playerInfo: PlayerInfo) -> float :
        return self.profileByPlayerInfo[playerInfo].mainRecord.point

    def getTrustReason(self, playerInfo: PlayerInfo) -> str :
        return self.profileByPlayerInfo[playerInfo].mainRecord.reason

    def getNegativeTrustReason(self, playerInfo: PlayerInfo, negativeReason: str = None) -> str :
        record: TrustRecord = self.profileByPlayerInfo[playerInfo].mainRecord
        if record.point < 0.0 :
            return record.reason
        elif negativeReason != None :
            return negativeReason
        else :
            return defaultReason

    def getPointerOrVoters(self, targetInfo: PlayerInfo) -> set[PlayerInfo] :
        if targetInfo in self.pointerOrVoterInfosByTargetInfo :
            return self.pointerOrVoterInfosByTargetInfo[targetInfo]
        else :
            return set()

    def getEffectiveCitizenCount(self) :
        return self.gameState.getPlayerCount() - 2 * self.gameState.getMafiaCount() + 1

    def _updateTrustRecordsByPlayerRemoved(self, removedPlayerInfo: PlayerInfo, removeReason: RemoveReason) :
        if removedPlayerInfo not in self.everPointerInfosByTargetInfo :
            return

        effectiveCitizenCount: int = self.getEffectiveCitizenCount()

        if removedPlayerInfo.role != Role.MAFIA :
            # He pointed out the citizen
            point: float = -50.0 / effectiveCitizenCount
            removedPlayerPoint = self.profileByPlayerInfo[removedPlayerInfo].mainRecord.point
            if removedPlayerPoint < -50.0 :
                point *= (100.0 + removedPlayerPoint) / 50.0

            for playerInfo in self.everPointerInfosByTargetInfo[removedPlayerInfo] :
                self.profileByPlayerInfo[playerInfo].addRecord(TrustRecord(
                    point=point,
                    reason='He pointed out the citizen.',
                ))
                point *= 0.5

            # He didn't vote for the citizen
            if removeReason == RemoveReason.VOTE :
                voteData: VoteData = self.gameState.getCurrentVoteData()
                notVotersCount: int = len(voteData.notVoteTargetPlayers)
                if notVotersCount > 0 :
                    point: float = 30.0 / (notVotersCount * effectiveCitizenCount)
                    for player in voteData.notVoteTargetPlayers :
                        self.profileByPlayerInfo[player.info].addRecord(TrustRecord(
                            point=point,
                            reason='He didn\'t vote for the citizen.',
                        ))

        else :
            # He pointed out the mafia
            point: float = 80.0 / self.gameState.getMafiaCount()
            for playerInfo in self.everPointerInfosByTargetInfo[removedPlayerInfo] :
                self.profileByPlayerInfo[playerInfo].addRecord(TrustRecord(
                    point=point,
                    reason='He pointed out the mafia.',
                ))
                point *= 0.5

            # He didn't vote for the mafia
            if removeReason == RemoveReason.VOTE :
                voteData: VoteData = self.gameState.getCurrentVoteData()
                notVotersCount: int = len(voteData.notVoteTargetPlayers)
                if notVotersCount > 0 :
                    point: float = -100 / notVotersCount
                    for player in voteData.notVoteTargetPlayers :
                        self.profileByPlayerInfo[player.info].addRecord(TrustRecord(
                            point=point,
                            reason='He didn\'t vote for the mafia.',
                        ))

            # He was pointed at by the mafia
            if removedPlayerInfo in self.mafiaPointingData :
                for playerInfo, point in self.mafiaPointingData[removedPlayerInfo].items() :
                    self.profileByPlayerInfo[playerInfo].addRecord(TrustRecord(
                        point=point,
                        reason='He was pointed at by the mafia.',
                    ))

    def _checkAndUpdateTrustStateStep1(self, player: Player, profile: TrustProfile) :
        if player.publicRole == Role.MAFIA :
            profile.setState(
                state=TrustState.CONFIRMED_MAFIA,
                reason='He revealed that he is a mafia.',
            )
            return

        if player.isContradictoryRole[0] :
            roleBefore, roleAfter = player.isContradictoryRole[1]
            profile.setState(
                state=TrustState.CONFIRMED_MAFIA,
                reason=f'He initially claimed his role was {roleBefore.name.lower()}, but now he claims to be {roleAfter.name.lower()}.',
            )
            return

        if player.publicRole == Role.POLICE :
            if not self.isPoliceLive :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='Despite the police being already eliminated, he claims his role is a police.',
                )
                return

            if len(self.verifiedPoliceInfos) > 0 and player.info not in self.verifiedPoliceInfos :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='Although there was already a police officer who had caught a mafia, he claimed to be the police.',
                )
                return

            mafiaEstimationCount = 0
            citizenEstimationCount = 0

            for estimation in player.estimationsAsPolice.values() :
                p = self.gameState.getPlayerByInfo(estimation.playerInfo)
                if p.publicRole == Role.POLICE and estimation.role != Role.MAFIA :
                    profile.setState(
                        state=TrustState.CONFIRMED_MAFIA,
                        reason=f'He claimed that {p.info.name} is a citizen, but {p.info.name} claims his role is a police.',
                    )
                    return

                if not p.isLive and ((p.info.role == Role.MAFIA) != (estimation.role == Role.MAFIA)) :
                    profile.setState(
                        state=TrustState.CONFIRMED_MAFIA,
                        reason='He incorrectly announced the role of an eliminated player.',
                    )
                    return

                if estimation.role == Role.MAFIA :
                    mafiaEstimationCount += 1
                else :
                    citizenEstimationCount += 1

            if self.gameState.gameInfo.mafiaCount < mafiaEstimationCount :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='There are too many mafia in his investigation results.',
                )
                return

            if self.gameState.gameInfo.citizenCount < citizenEstimationCount :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='There are too many citizens in his investigation results.',
                )
                return

            if self.gameState.round < len(player.estimationsAsPolice) :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='There are contradictions in his investigation results. He has presented more investigation results than what is possible in the current round.',
                )
                return

        if player.publicRole == Role.DOCTOR :
            if not self.isDoctorLive :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='Despite the doctor being already eliminated, he claims his role is a doctor.',
                )
                return

            citizenEstimationCount = 0

            for estimation in player.estimationsAsDoctor.values() :
                p = self.gameState.getPlayerByInfo(estimation.playerInfo)
                if p.publicRole == Role.DOCTOR and estimation.role != Role.MAFIA :
                    profile.setState(
                        state=TrustState.CONFIRMED_MAFIA,
                        reason=f'He claimed that {p.info.name} is a citizen, but {p.info.name} claims his role is a doctor.',
                    )
                    return

                if not p.isLive and p.info.role == Role.MAFIA and estimation.role != Role.MAFIA :
                    profile.setState(
                        state=TrustState.CONFIRMED_MAFIA,
                        reason='He incorrectly announced the role of an eliminated player.',
                    )
                    return

                if estimation.role == Role.MAFIA :
                    profile.setState(
                        state=TrustState.CONFIRMED_MAFIA,
                        reason='The doctor cannot identify who the mafia is even after successfully treating someone, but he pointed out a mafia member.',
                    )
                    return

                citizenEstimationCount += 1

            if citizenEstimationCount > len(self.healSucceededList) :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='He said he saved more citizens than the number of failed assassinations.',
                )
                return

            if self.gameState.gameInfo.citizenCount < citizenEstimationCount :
                profile.setState(
                    state=TrustState.CONFIRMED_MAFIA,
                    reason='There are too many citizens in the number of people he saved.',
                )
                return

        profile.setState(TrustState.NORMAL)

    def _checkAndUpdateTrustStateStep2(self) :
        if self.onePublicPolicePlayerInfo != None :
            policePlayer: Player = self.gameState.getPlayerByInfo(self.onePublicPolicePlayerInfo)
            policeProfile: TrustProfile = self.profileByPlayerInfo[self.onePublicPolicePlayerInfo]

            if policeProfile.state == TrustState.NORMAL :
                # VERIFIED_POLICE and CLAIMED_POLICE
                if self.onePublicPolicePlayerInfo in self.verifiedPoliceInfos :
                    policeProfile.setState(TrustState.VERIFIED_POLICE)
                else :
                    policeProfile.setState(TrustState.CLAIMED_POLICE)

                # CONFIRMED_MAFIA and CONFIRMED_CITIZEN
                for estimation in policePlayer.estimationsAsPolice.values() :
                    estimatedPlayerProfile: TrustProfile = self.profileByPlayerInfo[estimation.playerInfo]

                    if estimation.role == Role.MAFIA :
                        estimatedPlayerProfile.setState(
                            state=TrustState.CONFIRMED_MAFIA,
                            reason='The police identified him as a mafia member.',
                        )
                    else :
                        estimatedPlayerProfile.setState(
                            state=TrustState.CONFIRMED_CITIZEN,
                            reason='The police identified him as a citizen member.',
                        )

        # CLAIMED_DOCTOR
        if self.onePublicDoctorPlayerInfo != None :
            doctorProfile: TrustProfile = self.profileByPlayerInfo[self.onePublicDoctorPlayerInfo]
            if doctorProfile.state == TrustState.NORMAL :
                doctorProfile.setState(TrustState.CLAIMED_DOCTOR)

        # TARGETED_TRUSTED
        for pointerInfo, targetInfo in self.pointedTrustedTarget :
            targetProfile: TrustProfile = self.profileByPlayerInfo[targetInfo]
            if not targetProfile.isTargetable() :
                pointerProfile: TrustProfile = self.profileByPlayerInfo[pointerInfo]
                if pointerProfile.state == TrustState.NORMAL :
                    pointerProfile.setState(TrustState.TARGETED_TRUSTED)

    def _updateOnePublicPolicePlayerInfo(self) :
        if len(self.publicPolicePlayerInfos) == 1 :
            self.onePublicPolicePlayerInfo = next(iter(self.publicPolicePlayerInfos))
        else :
            self.onePublicPolicePlayerInfo = None

    def _updateOnePublicDoctorPlayerInfo(self) :
        if len(self.publicDoctorPlayerInfos) == 1 :
            self.onePublicDoctorPlayerInfo = next(iter(self.publicDoctorPlayerInfos))
        else :
            self.onePublicDoctorPlayerInfo = None
