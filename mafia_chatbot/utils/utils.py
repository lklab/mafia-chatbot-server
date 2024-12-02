import asyncio
from typing import Callable

async def getCuiInputAsync(text) -> str :
    return await asyncio.get_running_loop().run_in_executor(None, input, text)

async def waitUntil(condition: Callable[[], bool], interval=0.1):
    while not condition():
        await asyncio.sleep(interval)
