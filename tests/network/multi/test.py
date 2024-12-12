import asyncio
from multiprocessing import Process, Queue

class Data :
    def __init__(self, value: int) :
        self.value: int = value

async def worker(queue) :
    """서브프로세스가 실행할 함수"""
    for i in range(5):
        queue.put(Data(i))
        await asyncio.sleep(1)
    queue.put(None)  # 종료 신호

def sub(queue) :
    asyncio.run(worker(queue))

async def async_reader(queue):
    """Queue로부터 데이터를 비동기적으로 읽음"""
    loop = asyncio.get_running_loop()
    while True:
        msg = await loop.run_in_executor(None, queue.get)
        if msg is None:  # 종료 신호 확인
            break
        print(f"Received: {msg.value}")

async def main():
    queue = Queue()
    p = Process(target=sub, args=(queue,))
    p.start()

    task = asyncio.create_task(async_reader(queue))

    for i in range(3) :
        print('main running...')
        await asyncio.sleep(1)

    try:
        await task
    finally:
        p.join()

if __name__ == '__main__' :
    asyncio.run(main())
