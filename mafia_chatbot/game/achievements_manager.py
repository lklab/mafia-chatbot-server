from mafia_chatbot.game.game_state import GameState, VoteData
from mafia_chatbot.game.game_end_info import GameEndReason
from mafia_chatbot.game.player_info import Role
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.strategy import Strategy
from mafia_chatbot.game.chat_data import ChatType
from mafia_chatbot.game.player_info import PlayerInfo
from mafia_chatbot.game.game_logger import GameLogger, TAG

from mafia_chatbot.network.messages import *

class AchievementsManager :
    def __init__(self, gameState: GameState) :
        self.gameState = gameState
        self.logger: GameLogger = gameState.logger

        self.killCount: int = 0
        self.publicMafias: set[Player] = set()

    def onGameStart(self) :
        if len(self.gameState.userPlayers) == 10 :
            for player in self.gameState.userPlayers :
                self._sendUnlock(player, 'is_this_an_ai_game') # 인간 플레이어 10명이 함께 게임하기

    def onGameEnd(self, reason: GameEndReason) :
        if self._checkPlayerCountCondition(10, 2) :
            for player in self.gameState.userPlayers :
                if player.info.role == Role.CITIZEN and reason == GameEndReason.CITIZEN_WIN :
                    self._sendUnlock(player, 'mafia_free_mondays') # 10명/2명 게임에서 시민으로 생존 및 승리하기

                elif player.info.role == Role.MAFIA and reason == GameEndReason.MAFIA_WIN :
                    self._sendUnlock(player, 'catch_me_if_you_can') # 10명/2명 게임에서 마피아로 생존 및 승리하기
                    if player.publicRole == Role.POLICE :
                        self._sendUnlock(player, 'true_lies') # 10명/2명 게임에서 마피아로 경찰인 척 한 후 생존 및 승리하기

                elif player.info.role == Role.POLICE and reason == GameEndReason.CITIZEN_WIN :
                    self._sendUnlock(player, 'case_closed') # 10명/2명 게임에서 경찰로 생존 및 승리하기
                    if player.publicRole == Role.CITIZEN :
                        self._sendUnlock(player, 'detective_where') # 10명/2명 게임에서 자신이 경찰임을 밝히지 않고 생존 및 승리하기

                elif player.info.role == Role.DOCTOR and reason == GameEndReason.CITIZEN_WIN :
                    self._sendUnlock(player, 'diagnosis_victory') # 10명/2명 게임에서 의사로 생존 및 승리하기
                    if len(player.healTargets) == 0 :
                        self._sendUnlock(player, 'wheres_the_doctor') # 10명/2명 게임에서 아무도 치료하지 않고 생존 및 승리하기

        elif self._checkPlayerCountCondition(10, 1) :
            for player in self.gameState.userPlayers :
                if player.info.role == Role.MAFIA and reason == GameEndReason.MAFIA_WIN :
                    self._sendUnlock(player, 'i_am_the_one_who_knocks') # 10명/1명 게임에서 마피아로 승리하기

        chatPlayerInfos: set[PlayerInfo] = set()
        for chat in self.gameState.chatList :
            if chat.type == ChatType.DISCUSSION and chat.sender != None :
                chatPlayerInfos.add(chat.sender)

        for player in self.gameState.userPlayers :
            if player.info not in chatPlayerInfos and (
                (player.info.role == Role.MAFIA and reason == GameEndReason.MAFIA_WIN) or
                (player.info.role != Role.MAFIA and reason == GameEndReason.CITIZEN_WIN)
            ) :
                self._sendUnlock(player, 'silence_is_golden') # 아무 말도 하지 않고 생존 및 승리하기

    def onStrategyUpdated(self, player: Player, strategy: Strategy) :
        if player.info.role == Role.MAFIA and player.publicRole == Role.MAFIA and player not in self.publicMafias :
            self.publicMafias.add(player)
            self._sendUnlock(player, 'honest_traitor') # 자신이 마피아임을 고백하기

    def onExecuted(self, targetInfo: PlayerInfo, voteData: VoteData) :
        if self._checkPlayerCountCondition(10, 2) and targetInfo.role == Role.MAFIA :
            for voter in voteData.getVoters(targetInfo) :
                if voter.info != targetInfo and voter.info.role == Role.MAFIA :
                    self._sendUnlock(voter, 'friends_dont_let_friends_live') # 10명/2명 게임에서 동료 마피아에게 투표해서 처형시키기

    def onKilled(self, target: Player) :
        if self._checkPlayerCountCondition(10, 2) :
            self.killCount += 1
            if self.killCount == 5 :
                for player in self.gameState.userPlayers :
                    if player.info.role == Role.MAFIA :
                        self._sendUnlock(player, 'hitman') # 10명/2명 게임에서 마피아로 5명 이상 암살하기

            if target.publicRole == Role.CITIZEN and target.info.role == Role.POLICE :
                for player in self.gameState.userPlayers :
                    if player.info.role == Role.MAFIA :
                        self._sendUnlock(player, 'the_lucky_shot') # 10명/2명 게임에서 자신을 공개하지 않은 경찰 암살하기

            if target.info.role == Role.MAFIA :
                for player in self.gameState.userPlayers :
                    if player != target and player.info.role == Role.MAFIA :
                        self._sendUnlock(player, 'et_tu_brute') # 10명/2명 게임에서 동료 마피아 암살하기

    def onTested(self, target: Player) :
        if self._checkPlayerCountCondition(10, 2) and target.info.role == Role.MAFIA :
            police: Player = self.gameState.policePlayer
            if len(police.testedMafias) == 2 :
                self._sendUnlock(police, 'aced_it') # 10명/2명 게임에서 경찰로 모든 마피아 조사해서 밝혀내기

    def onHealSucceeded(self) :
        if self._checkPlayerCountCondition(10, 2) :
            doctor: Player = self.gameState.doctorPlayer
            if len(doctor.healSuccesses) == 2 :
                self._sendUnlock(doctor, 'healer') # 10명/2명 게임에서 의사로 2명 이상 치료에 성공하기

    def _sendUnlock(self, player: Player, key: str) :
        message = game_pb2.UnlockAchievement()
        message.achievementKey = key

        if player.user != None and player.isLive :
            self.logger.log(TAG.ACHIEVEMENTS, f'{player.info.name}: Unlock achievement: {key}')
            player.user.send(message)

    def _checkPlayerCountCondition(self, playerCount: int, mafiaCount: int) -> bool :
        return self.gameState.gameInfo.playerCount == playerCount and self.gameState.gameInfo.mafiaCount == mafiaCount
