import asyncio

async def reapTask(task: asyncio.Task) :
    try :
        if not task.done():
            print('await task')
            await task
            print('task done')
    except asyncio.CancelledError :
        print('asyncio.CancelledError')
    except Exception as e:
        print(f"Unhandled exception in task: {e}")
    print('reap task completed')

async def myTask() :
    await asyncio.sleep(3)
    print('my task completed')

async def main() :
    task = asyncio.create_task(myTask())
    await asyncio.sleep(2)
    print('try stop my task')

    # task.cancel()
    asyncio.create_task(reapTask(task))

    await asyncio.sleep(2)
    print('end main logic')

asyncio.run(main())
