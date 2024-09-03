import json
import os

class LLM :
    def __init__(self) :
        pass
        # # load API key
        # with open('apikeys.json') as f:
        #     keys = json.load(f)

        # os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
        # os.environ["LANGCHAIN_TRACING_V2"] = "true"
        # os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

        # # setup model
        # from langchain_openai import ChatOpenAI
        # self.model = ChatOpenAI(
        #     model="gpt-3.5-turbo",
        # )
