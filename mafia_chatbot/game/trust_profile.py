from enum import Enum

from mafia_chatbot.game.player_info import PlayerInfo
from mafia_chatbot.game.game_logger import GameLogger, TAG

defaultReason = 'Due to a lack of information, you will suspect someone as the mafia, but it is only a guess. You might come up with a funny reason, or perhaps base your suspicion on something completely random like their tone of voice or the way they blinked.'

class TrustState(Enum) :
    NORMAL = 0
    CONFIRMED_MAFIA = 1
    CONFIRMED_CITIZEN = 2
    CLAIMED_POLICE = 3
    CLAIMED_DOCTOR = 4
    VERIFIED_POLICE = 5
    TARGETED_TRUSTED = 6

def normalizePoint(point: float) :
    return (point + 100.0) / 200.0

class TrustRecord :
    def __init__(self, point: float, reason: str = None) :
        if point < -100.0 :
            point = -100.0
        elif point > 100.0 :
            point = 100.0

        self.point: float = point
        self.reason: str = reason if reason != None else defaultReason
        self.negativeReason: str = self.reason if self.point < 0 else defaultReason

    def __str__(self) :
        return f'(point={self.point}, reason={self.reason})'

    def __repr__(self) :
        return self.__str__()

recordsByTrustStateDict: dict[TrustState, TrustRecord] = {
    TrustState.CONFIRMED_MAFIA   : TrustRecord(-100.0, 'He is definitely the Mafia.'),
    TrustState.CONFIRMED_CITIZEN : TrustRecord( 100.0, 'The police said he is a citizen.'),
    TrustState.CLAIMED_POLICE    : TrustRecord( 100.0, 'He claimed to be the police.'),
    TrustState.CLAIMED_DOCTOR    : TrustRecord( 100.0, 'He claimed to be the doctor.'),
    TrustState.VERIFIED_POLICE   : TrustRecord( 100.0, 'He is definitely the police.'),
    TrustState.TARGETED_TRUSTED  : TrustRecord(-100.0, 'He accused a player who seemed trustworthy as a citizen of being a mafia.'),
}

targetablesByTrustStateDict: dict[TrustState, bool] = {
    TrustState.NORMAL            : True,
    TrustState.CONFIRMED_MAFIA   : True,
    TrustState.CONFIRMED_CITIZEN : False,
    TrustState.CLAIMED_POLICE    : False,
    TrustState.CLAIMED_DOCTOR    : False,
    TrustState.VERIFIED_POLICE   : False,
    TrustState.TARGETED_TRUSTED  : True,
}

mustTargetingsByTrustStateDict: dict[TrustState, bool] = {
    TrustState.NORMAL            : False,
    TrustState.CONFIRMED_MAFIA   : True,
    TrustState.CONFIRMED_CITIZEN : False,
    TrustState.CLAIMED_POLICE    : False,
    TrustState.CLAIMED_DOCTOR    : False,
    TrustState.VERIFIED_POLICE   : False,
    TrustState.TARGETED_TRUSTED  : False,
}

class TrustProfile :
    def __init__(self, playerInfo: PlayerInfo, logger: GameLogger) :
        self.playerInfo = playerInfo
        self.logger = logger

        self.state: TrustState = TrustState.NORMAL
        self._mainRecord: TrustRecord = TrustRecord(0.0, defaultReason)
        self.mainRecord: TrustRecord = self._mainRecord

    def addRecord(self, record: TrustRecord) :
        if abs(self._mainRecord.point) < abs(record.point) :
            self._mainRecord = record
            if self.state == TrustState.NORMAL :
                self.mainRecord = record
                self.logger.log(TAG.TRUST, f'{self.playerInfo.name}: main record changed: state={self.state.name}, mainRecord={self.mainRecord}')

    def setState(self, state: TrustState, reason: str = None) :
        if state == TrustState.NORMAL :
            if self.state == state :
                return
            self.state = state
            self.mainRecord = self._mainRecord
            self.logger.log(TAG.TRUST, f'{self.playerInfo.name}: main record changed: state={self.state.name}, mainRecord={self.mainRecord}')

        else :
            record: TrustRecord = recordsByTrustStateDict[state]
            if reason != None :
                record = TrustRecord(record.point, reason)
            self.mainRecord = record
            self.logger.log(TAG.TRUST, f'{self.playerInfo.name}: main record changed: state={self.state.name}, mainRecord={self.mainRecord}')

    def isTargetable(self) -> bool :
        return targetablesByTrustStateDict[self.state]

    def isMustTargeting(self) -> bool :
        return mustTargetingsByTrustStateDict[self.state]
