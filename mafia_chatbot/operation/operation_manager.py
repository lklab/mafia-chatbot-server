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

    def getStateMessage(self, language: str) -> str :
        language = language.lower()
        if language in self.stateMessage :
            return self.stateMessage[language]
        else :
            return self.stateMessage['english']

    async def _readOpInfoTask(self) :
        while True :
            await asyncio.sleep(60)
            self._readOpInfo()

    def _readOpInfo(self) :
        with open('config/operation_info.json', encoding='utf-8') as f :
            info = json.load(f)

        self.requiredVersion: str = info['requiredVersion']
        self.operating: bool = info['operating']
        self.stateMessage: dict[str, str] = info['stateMessage']
        self.maintainEndTime: str = info['maintainEndTime']
        self.enableAds: bool = info['enableAds']

operationManager: OperationManager = OperationManager()
