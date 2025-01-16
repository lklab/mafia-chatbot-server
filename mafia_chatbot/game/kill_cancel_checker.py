import asyncio

from mafia_chatbot.game.player import Player
from mafia_chatbot.network.messages import *

class KillCancelChecker :
    def __init__(self, player: Player) :
        self.player = player
        self.waitTask: asyncio.Task = None
        self.userMessage: game_pb2.CancelKillWithAds = None

    def start(self) :
        if self.waitTask != None :
            return

        canCancelAssassinationWithAds = game_pb2.CanCancelKillWithAds()
        self.player.user.send(canCancelAssassinationWithAds)

        self.waitTask = asyncio.create_task(asyncio.sleep(3600))

    def setUserMessage(self, message: game_pb2.CancelKillWithAds) :
        if self.waitTask == None :
            return

        self.userMessage = message
        self.interrupt()

    def interrupt(self) :
        if self.waitTask == None :
            return

        self.waitTask.cancel()
        self.waitTask = None

    async def isCancel(self) -> bool :
        try :
            await self.waitTask
        except :
            pass

        self.waitTask = None
        return self.userMessage != None and self.userMessage.cancel
