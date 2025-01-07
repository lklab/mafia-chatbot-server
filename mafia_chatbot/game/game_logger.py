import logging
import datetime
import os
from enum import Enum
import traceback

class TAG(Enum) :
    INFO = 0
    CHAT = 1
    PHASE = 2
    DISCUSSION = 3
    STRATEGY = 4
    TRUST = 5
    LLM = 6
    NETWORK = 7
    ERROR = 99

class GameLogger :
    def __init__(self, gameId: str, path: str) :
        time = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        self.name = f'[{time}]_eval_{gameId}'
        logger = logging.getLogger(self.name)
        logger.setLevel(logging.DEBUG)

        os.makedirs(path, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(path, f'{self.name}.log'), encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter('%(asctime)s - %(message)s')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        self.logger = logger

    def log(self, tag: TAG, message: str) :
        self.logger.debug(f'[{tag.name}] {message}')

    def logError(self, message: str, e: Exception) :
        self.logger.error(f'[EXCEPTION] {message}: {e}')
        self.logger.error(traceback.format_exc())

    def close(self) :
        for handler in self.logger.handlers:
            handler.close()
            self.logger.removeHandler(handler)

class FakeGameLogger :
    def log(self, tag: TAG, message: str) :
        pass
    def logError(self, message: str, e: Exception) :
        pass
    def close(self) :
        pass
