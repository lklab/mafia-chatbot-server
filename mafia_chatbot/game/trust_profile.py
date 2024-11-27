from enum import Enum

defaultReason = 'Due to a lack of information, You will randomly suspect someone as the mafia.'

class TrustState(Enum) :
    NORMAL = 0
    CONFIRMED_MAFIA = 1
    CONFIRMED_CITIZEN = 2
    CLAIMED_POLICE = 3
    CLAIMED_DOCTOR = 4
    VERIFIED_POLICE = 5
    TARGETED_TRUSTED = 6

class TrustRecord :
    def __init__(self, point: float, reason: str = None) :
        self.point: float = point
        self.reason: str = reason if reason != None else defaultReason
        self.negativeReason: str = self.reason if self.point < 0 else defaultReason

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
    def __init__(self) :
        self.state: TrustState = TrustState.NORMAL
        self._mainRecord: TrustRecord = TrustRecord(0.0, defaultReason)
        self.mainRecord: TrustRecord = self._mainRecord

    def addRecord(self, record: TrustRecord) :
        if abs(self._mainRecord.point) < abs(record.point) :
            self._mainRecord = record
            if self.state == TrustState.NORMAL :
                self.mainRecord = record

    def setState(self, state: TrustState, reason: str = None) :
        self.state = state

        if state == TrustState.NORMAL :
            self.mainRecord = self._mainRecord

        else :
            record: TrustRecord = recordsByTrustStateDict[state]
            if reason != None :
                record = TrustRecord(record.point, reason)
            self.mainRecord = record

    def isTargetable(self) -> bool :
        return targetablesByTrustStateDict[self.state]

    def isMustTargeting(self) -> bool :
        return mustTargetingsByTrustStateDict[self.state]
