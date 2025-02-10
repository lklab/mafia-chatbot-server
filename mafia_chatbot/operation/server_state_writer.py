import json
from typing import Callable
import asyncio
import os

class ServerStateWriter :
    def __init__(
            self,
            gameCountGetter: Callable[[], int],
            roomCountGetter: Callable[[], int]
        ) :

        self.gameCountGetter = gameCountGetter
        self.roomCountGetter = roomCountGetter

        self.path = 'op_log'
        os.makedirs(self.path, exist_ok=True)

        asyncio.create_task(self._writer())

    async def _writer(self) :
        while True :
            self._write()
            await asyncio.sleep(60)

    def _write(self) :
        data = {}
        data['gameCount'] = self.gameCountGetter()
        data['roomCount'] = self.roomCountGetter()

        with open(os.path.join(self.path, 'server_state.json'), "w", encoding="utf-8") as f :
            json.dump(data, f, ensure_ascii=False, indent=4)
