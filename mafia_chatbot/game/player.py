import random
import numpy as np

from mafia_chatbot.game.client_player import ClientPlayer
from mafia_chatbot.game.player_info import PlayerInfo, roleToProtoDict
from mafia_chatbot.game.strategy import *

from mafia_chatbot.network.messages import *

class Player :
    pass

class RemoveReason(Enum) :
    LIVE = 0
    VOTE = 1
    KILL = 2
    OBSERVER = 3

removeReasonToProtoDict: dict[RemoveReason, game_pb2.RemoveReason] = {
    RemoveReason.LIVE: game_pb2.RemoveReason.REMOVE_LIVE,
    RemoveReason.VOTE: game_pb2.RemoveReason.REMOVE_EXECUTED,
    RemoveReason.KILL: game_pb2.RemoveReason.REMOVE_ASSASSINATED,
    RemoveReason.OBSERVER: game_pb2.RemoveReason.REMOVE_OBSERVER,
}

class Player :
    def __init__(self, name: str, tone: str, isHuman: bool, client: ClientPlayer) :
        # player data
        self.info = PlayerInfo(name, tone, isHuman, isHuman and client == None)
        self.client = client
        self.isLive = True
        self.removeReason = RemoveReason.LIVE

        # personal factors
        self.trustSensitivity: float = random.uniform(0.0, 2.0) # 값이 클수록 타겟을 정할 때 신뢰도 값을 많이 반영함
        self.conformity: float = random.uniform(0.5, 1.5) # 값이 클수록 더 적은 수의 플레이어에게 지목되더라도 그 플레이어를 지목함
        self.claimeFactorForMafia: float = random.uniform(0.0, 0.2) # 마피아가 경찰 주장을 할 확률
        self.claimeFactorForReal: float = random.uniform(1.0, 2.0) # 경찰/의사인 경우 1보다 커야 함
        self.mainHealFactor: float = random.uniform(0.7, 1.0) # 0.9
        self.isFakePolice: bool = False
        self.positiveness: float = random.uniform(0.1, 1.0) # 토론 참여 적극성

        # strategies
        self.discussionStrategy: Strategy = None
        self.voteStrategy: VoteStrategy = None
        self.allDiscussionStrategies: list[Strategy] = []
        self.allVoteStrategies: list[VoteStrategy] = []

        # strategy summary
        self.publicRole = Role.CITIZEN
        self.isPublicRoleChanged = False
        # 모순되는 역할 변경을 한 이력이 있는지 여부, tuple[모순여부, tuple[기존 역할, 주장하는 역할]]
        self.isContradictoryRole: tuple[bool, tuple[Role, Role]] = (False, (None, None))
        self.voteHistory: list[PlayerInfo] = []
        self.estimationsAsPolice: dict[PlayerInfo, Estimation] = {}
        self.estimationsAsDoctor: dict[PlayerInfo, Estimation] = {}

        # police's private data
        self.testResults: dict[Player, Role] = {}
        self.testedMafias: list[Player] = []
        self.testedCitizens: list[Player] = []
        self.lastTestedTarget: Player = None

        # doctor's private data
        self.healSuccesses: set[Player] = set()
        self.lastHealSuccess: Player = None

        # human chating count
        self.maxChatingCount = 5
        self.remainChatingCount = 0

    def __str__(self) :
        return self.info.__str__()

    def __repr__(self) :
        return self.info.__repr__()

    def getFullRepr(self) :
        return (
            f'{self.info.name}: '
            f'id={self.info.id}, '
            f'isHuman={self.info.isHuman}, '
            f'role={self.info.role.name}, '
            f'tone={self.info.tone}, '
            f'trustSensitivity={self.trustSensitivity:.2f}, '
            f'conformity={self.conformity:.2f}, '
            f'claimeFactorForMafia={self.claimeFactorForMafia:.2f}, '
            f'claimeFactorForReal={self.claimeFactorForReal:.2f}, '
            f'mainHealFactor={self.mainHealFactor:.2f}, '
            f'isFakePolice={self.isFakePolice}, '
            f'positiveness={self.positiveness:.2f}'
        )

    def setDiscussionStrategy(self, round: int, strategy: Strategy) :
        self.discussionStrategy = strategy

        # update allDiscussionStrategies
        self.expandList(self.allDiscussionStrategies, round + 1)
        self.allDiscussionStrategies[round] = strategy

        # update publicRole
        if self.publicRole != strategy.publicRole :
            # 시민에서 다른 역할로의 변경 허용
            if self.publicRole == Role.CITIZEN :
                self.publicRole = strategy.publicRole
                self.isPublicRoleChanged = True

            # 다른 역할에서 시민으로의 역할 변경 무시
            elif strategy.publicRole == Role.CITIZEN :
                self.isPublicRoleChanged = False

            # 마피아로 주장한 적이 있는 경우 무시
            elif self.publicRole == Role.MAFIA :
                self.isPublicRoleChanged = False

            # 그 외의 경우(경찰 <-> 의사) 모순적인 역할 변경으로 처리
            else :
                self.isPublicRoleChanged = False
                self.isContradictoryRole = (True, (self.publicRole, strategy.publicRole))

        else :
            self.isPublicRoleChanged = False

        for assumption in strategy.assumptions :
            # update estimationsAsPolice
            if assumption.assumptionType == AssumptionType.TEST_RESULT :
                for estimation in assumption.estimations :
                    self.estimationsAsPolice[estimation.playerInfo] = estimation
            # update estimationsAsDoctor
            if assumption.assumptionType == AssumptionType.HEAL_SUCCESS :
                for estimation in assumption.estimations :
                    self.estimationsAsDoctor[estimation.playerInfo] = estimation

    def setVoteStrategy(self, round: int, strategy: VoteStrategy) :
        self.voteStrategy = strategy

        # update allVoteStrategies
        self.expandList(self.allVoteStrategies, round + 1)
        self.allVoteStrategies[round] = strategy

        # update voteHistory
        self.expandList(self.voteHistory, round + 1)
        self.voteHistory[round] = strategy.mainTarget

    def getDiscussionStrategy(self, round: int) -> Strategy :
        if round >= 0 and round < len(self.allDiscussionStrategies) :
            return self.allDiscussionStrategies[round]
        else :
            return None

    def getVoteStrategy(self, round: int) -> VoteStrategy :
        if round >= 0 and round < len(self.allVoteStrategies) :
            return self.allVoteStrategies[round]
        else :
            return None

    def getDiscussion(self) :
        return self.discussionStrategy.assumptionsToStr()

    def setRemoved(self, removeReason: RemoveReason) :
        self.isLive = False
        self.removeReason = removeReason

    def addTestResult(self, player: Player, role: Role) :
        if player != None :
            self.testResults[player] = role

            if role == Role.MAFIA :
                self.testedMafias.append(player)
            else :
                self.testedCitizens.append(player)

        self.lastTestedTarget = player

    def addHealSuccess(self, player: Player) :
        if player != None :
            self.healSuccesses.add(player)
        self.lastHealSuccess = player

    def getRolePrompt(self) -> str :
        if self.isPublicRoleChanged :
            return f'You must claim that your role is {self.info.role.name.lower()}.'
        else :
            return ''

    def reloadChatingCount(self) :
        self.remainChatingCount = self.maxChatingCount

    def clearChatingCount(self) :
        self.remainChatingCount = 0

    def createProtoMessage(self, receiver: Player) -> game_pb2.Player :
        message = game_pb2.Player()
        self.toProtoMessage(receiver, message)
        return message

    def toProtoMessage(self, receiver: Player, message_out: game_pb2.Player) :
        message_out.id = self.info.id
        message_out.name = self.info.name

        if not self.isLive or self == receiver :
            message_out.role = roleToProtoDict[self.info.role]
        elif receiver.info.role == Role.POLICE and self in receiver.testResults :
            message_out.role = roleToProtoDict[Role.MAFIA] if self.info.role == Role.MAFIA else roleToProtoDict[Role.CITIZEN]
        elif receiver.info.role == Role.MAFIA and self.info.role == Role.MAFIA :
            message_out.role = roleToProtoDict[Role.MAFIA]
        else :
            message_out.role = game_pb2.Role.Role_UNKNOWN

        message_out.isLive = self.isLive
        message_out.removeReason = removeReasonToProtoDict[self.removeReason]

    def expandList(self, l: list, size: int, fillValue = None) :
        for _ in range(len(l), size) :
            l.append(fillValue)

    def _getRandom(minValue: float, maxValue: float, mean: float, stdDev: float) -> float :
        value = np.random.normal(loc=mean, scale=stdDev)
        value = np.clip(value, minValue, maxValue)
        return value
