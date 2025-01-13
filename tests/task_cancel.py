import asyncio

async def infLoop() :
    while True :
        try :
            await asyncio.sleep(1)
        except Exception as e :
            print(f'infLoop exception: {e}')
            return
        except asyncio.CancelledError as e :
            print(f'infLoop CancelledError: {e}')
            return
        print('loop!')

async def main() :
    task = asyncio.create_task(infLoop())
    await asyncio.sleep(10)
    print('cancel!')
    task.cancel()
    await asyncio.sleep(10)
    try :
        await task
    except Exception as e :
        print(f'main exception: {e}')
    except asyncio.CancelledError as e :
        print(f'main CancelledError: {e}')

asyncio.run(main())
