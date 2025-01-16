import asyncio

async def cancel(task: asyncio.Task) :
    await asyncio.sleep(1)
    print('cancel')
    task.cancel()

async def main() :
    task = asyncio.create_task(asyncio.sleep(10))
    # asyncio.create_task(cancel(task))

    try :
        await task
        print('done')
    except :
        print('except')

asyncio.run(main())
