if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

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
    temperature=0.2,
)

# setup prompt
template = (
    "You are tasked with evaluating names submitted by users for use in a Mafia game to determine if they are suitable. If the name is any of the following:"
    "\n"
    "A term commonly used in Mafia games (e.g., \"citizen,\" \"mafia,\" \"police,\" \"doctor,\" \"vote,\" \"execution\")."
    "\n"
    "A personal pronoun (e.g., \"I,\" \"you,\" \"we\")."
    "\n"
    "A word that is generally not recognized as a name (e.g., \"unknown,\" \"no\")."
    "\n"
    "Return \"true\". Otherwise, return \"false\"."
    "\n\n"
    "{name}"
)
prompt = PromptTemplate.from_template(template)

parser = StrOutputParser()

# setup chain
chain = prompt | model | parser

names = [
    '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
    '연우', '소윤', '유진', '성민', '은비', '재현', '예린',
    '태윤', '민지', '시우', '세영', '아린', '진우', '경찰',
]
names2 = [
    '경찰', '마피아', '아님', '바보', '몰라', '모름', 'killer', 'mafia',
]

# for name in names2 :
#     result = chain.invoke({
#         'name' : name,
#     })
#     print(f'{name}: {result}')

import mafia_chatbot.utils.name_bank as NameBank

async def main() :
    global names
    for name in names :
        result = await NameBank.checkName(name)
        print(f'{name}: {result.name}')

asyncio.run(main())
