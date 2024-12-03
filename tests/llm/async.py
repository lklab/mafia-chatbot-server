import json
import os
import asyncio

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# load API key
with open('apikeys.json') as f:
    keys = json.load(f)

os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
if 'LANGCHAIN_API_KEY' in keys :
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

# setup model
model = ChatOpenAI(
    model="gpt-3.5-turbo",
)

# setup prompt
template = '{country}의 수도는 어디인가요?'
prompt = PromptTemplate.from_template(template)

parser = StrOutputParser()

# setup chain
chain = prompt | model | parser

async def ainvoke(country: str) :
    result = await chain.ainvoke({'country' : country})
    print(result)

asyncio.run(ainvoke('대한민국'))
