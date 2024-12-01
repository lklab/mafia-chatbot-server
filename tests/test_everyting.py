import asyncio

class MyClass :
    pass

class MyClass :
    def __init__(self, value) :
        self.value = value

    def _doOne(self) :
        print('one')

    def _doTwo(self) :
        print('two')

    myDict = {
        1 : _doOne,
        2 : _doTwo,
    }

    def doSomething(self) :
        MyClass.myDict[self.value](self)

async def asyncInput() :
    return await asyncio.get_running_loop().run_in_executor(None, input, 'input!')

async def asyncMain() :
    task = asyncio.create_task(asyncInput())

    for i in range(5) :
        print(i)
        await asyncio.sleep(1)

    value = await task
    print(f'input is {value}')

# myClass = MyClass(1)
# myClass.doSomething()

# asyncio.run(asyncMain())

async def test1() :
    print('test1')
    await asyncio.sleep(1) # do some async method
    await test1()

async def test2() :
    print('test2')
    await asyncio.sleep(1)
    asyncio.create_task(test2())

asyncio.run(test2())
