if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import os
import json
import asyncio

# load API key
with open('config/apikeys.json') as f:
    keys = json.load(f)

os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
os.environ["GOOGLE_API_KEY"] = keys['GOOGLE_API_KEY']

if 'LANGCHAIN_API_KEY' in keys :
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

import mafia_chatbot.utils.name_bank as NameBank

NameBank.initialize()
# nameList: list[tuple[str, str]] = []
# for i in range(10) :
#     name = NameBank.NAMES['korean'][i]
#     nameList.append((name, NameBank.ENGLISH_NAMES['korean'][name]))

# model = ChatGoogleGenerativeAI(
#     model="gemini-1.5-flash",
#     temperature=0.1,
# )

# names = '\n'.join(map(lambda p: f'"{p[0]}": "{p[1]}"', nameList))
# template = (
#     f"Translate the following ##sentence## into English without altering its original meaning. Use the specified words from ##names## for proper nouns and the terms from ##terms## to ensure consistent vocabulary for similar or identical meanings. If ##sentence## does not contain meaningful content (e.g., numbers, empty strings, or non-sentential fragments), return an empty string instead."
#     "\n\n"
#     "##sentence##"
#     "\n"
#     "{sentence}"
#     "\n\n"
#     "##names##"
#     "\n"
#     f"{names}"
#     "\n\n"
#     "##terms##"
#     "\n"
#     "citizen, mafia, police, doctor, vote, execution, assassination, investigation, healing"
# )
# prompt = PromptTemplate.from_template(template)

# # setup parser
# parser = StrOutputParser()

# # setup chain
# chain = prompt | model | parser

async def ainvoke(sentence) :
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2,
        # other params...
    )

    messages = [
        (
            "system",
            "You are a helpful assistant that translates English to Korean. Translate the user sentence.",
        ),
        ("human", "I love programming."),
    ]
    response = await llm.ainvoke(messages)

    # response = await llm.ainvoke({
    #     'sentence' : sentence,
    # })
    print(response)

async def main() :
    tasks: list[asyncio.Task] = []
    for i in range(10) :
        tasks.append(asyncio.create_task(ainvoke('나는 경찰이야')))
    
    for task in tasks :
        try :
            await task
        except Exception as e :
            print(f'error: {e}')

asyncio.run(main())

# llm = ChatGoogleGenerativeAI(
#     model="gemini-1.5-flash",
#     temperature=0,
#     max_tokens=None,
#     timeout=None,
#     max_retries=2,
#     # other params...
# )

# messages = [
#     (
#         "system",
#         "You are a helpful assistant that translates English to Korean. Translate the user sentence.",
#     ),
#     ("human", "I love programming."),
# ]
# ai_msg = llm.invoke(messages)
# print(ai_msg)
