import asyncio
import json

class OperationManager :
    def __init__(self) :
        self.initialized: bool = False
        self._readOpInfo()

    def initialize(self) :
        if self.initialized :
            return
        self.initialized = True

        self.readOpInfoTask = asyncio.create_task(self._readOpInfoTask())

    async def _readOpInfoTask(self) :
        while True :
            await asyncio.sleep(1)
            self._readOpInfo()

    def _readOpInfo(self) :
        with open('operation_info.json') as f :
            info = json.load(f)

        self.requiredVersion: str = info['requiredVersion']

operationManager: OperationManager = OperationManager()
