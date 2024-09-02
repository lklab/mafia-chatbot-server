import json
import os

class GameManager :
    def __init__(self) :
        # load API key
        with open('apikeys.json') as f:
            keys = json.load(f)

        os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

        # setup model
        from langchain_openai import ChatOpenAI
        self.model = ChatOpenAI(
            model="gpt-3.5-turbo",
        )

    def start(self) :
        try :
            while True :
                message = input()
                response = self.model.invoke(message)
                print(response.content)
        except KeyboardInterrupt :
            print('terminated')
