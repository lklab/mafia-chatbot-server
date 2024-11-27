from mafia_chatbot.game.game_state import GameState, VoteData, RemoveReason
from mafia_chatbot.game.trust_profile import TrustProfile, TrustRecord
from mafia_chatbot.game.player_info import PlayerInfo, Role
from mafia_chatbot.game.strategy import Strategy

class TrustRecorder :
    def __init__(self, gameState: GameState) :
        self.gameState = gameState

        self.profiles: list[TrustProfile]
        self.profileByPlayerInfo: dict[PlayerInfo, TrustProfile]
        for player in gameState.players :
            profile: TrustProfile = TrustProfile()
            self.profiles.append(profile)
            self.profileByPlayerInfo[player.info] = profile

    def startNewRound(self) :
        self.pointerInfosByTargetInfo: dict[PlayerInfo, list[PlayerInfo]] = {}
        self.pointerInfoSetByTargetInfo: dict[PlayerInfo, set[PlayerInfo]] = {}

        self.everPointerPlayerInfos: set[PlayerInfo] = set()
        self.mafiaPointingData: dict[PlayerInfo, dict[PlayerInfo, float]] = {}

    def discussionStrategyUpdated(self, playerInfo: PlayerInfo, strategy: Strategy) :
        for estimation in strategy.mafiaEstimations :
            targetInfo: PlayerInfo = estimation.playerInfo

            if targetInfo not in self.pointerInfosByTargetInfo :
                self.pointerInfosByTargetInfo[targetInfo] = []
                self.pointerInfoSetByTargetInfo[targetInfo] = set()

            if playerInfo not in self.pointerInfosByTargetInfo[targetInfo] :
                self.pointerInfosByTargetInfo[targetInfo].append(playerInfo)
                self.pointerInfoSetByTargetInfo[targetInfo].add(playerInfo)

        self.everPointerPlayerInfos.add(playerInfo)

        if playerInfo.role == Role.MAFIA :
            if playerInfo not in self.mafiaPointingData :
                self.mafiaPointingData[playerInfo] = {}

            basePoint: float = 100.0 / (len(self.everPointerPlayerInfos) * (self.gameState.getMafiaCount() - 1))

            for estimation in strategy.mafiaEstimations :
                targetInfo: PlayerInfo = estimation.playerInfo
                point: float = basePoint * (self._getTrustPoint(targetInfo) + 100) / 200.0
                point = min(point, 80.0)
                self.mafiaPointingData[playerInfo][targetInfo] = point

    def playerRemoved(self, removedPlayerInfo: PlayerInfo, removeReason: RemoveReason) :
        if removedPlayerInfo not in self.pointerInfosByTargetInfo :
            return

        effectiveCitizenCount: int = self._getEffectiveCitizenCount()

        if removedPlayerInfo.role != Role.MAFIA :
            # He pointed out the citizen
            point: float = -50.0 / effectiveCitizenCount
            removedPlayerPoint = self.profileByPlayerInfo[removedPlayerInfo].mainRecord.point
            if removedPlayerPoint < -50.0 :
                point *= (100.0 + removedPlayerPoint) / 50.0

            for playerInfo in self.pointerInfosByTargetInfo[removedPlayerInfo] :
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
            for playerInfo in self.pointerInfosByTargetInfo[removedPlayerInfo] :
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

    def _getEffectiveCitizenCount(self) :
        return self.gameState.getPlayerCount() - 2 * self.gameState.getMafiaCount() + 1

    def _getTrustPoint(self, playerInfo: PlayerInfo) -> float :
        return self.profileByPlayerInfo[playerInfo].mainRecord.point
