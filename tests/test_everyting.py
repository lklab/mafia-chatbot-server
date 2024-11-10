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

myClass = MyClass(1)
myClass.doSomething()
