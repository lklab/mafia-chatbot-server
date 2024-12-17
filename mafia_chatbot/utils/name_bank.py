from enum import Enum
import re
import json
import os

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

NAMES: dict[str, list[str]] = {
    "english" : [
        "Oliver", "Emma", "Noah", "Ava", "Liam", "Sophia", "Mason", "Isabella",
        "James", "Mia", "Benjamin", "Amelia", "Ethan", "Harper", "Lucas",
        "Charlotte", "Henry", "Evelyn", "Jack", "Grace",
        "William", "Ella", "Logan", "Chloe", "Daniel", "Lily", "Alexander", "Hannah",
        "Michael", "Emily", "Samuel", "Aria", "Matthew", "Scarlett", "Joseph", "Madison",
        "David", "Abigail", "Sebastian", "Nora",
    ],
    'korean' : [
        '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
        '연우', '소윤', '유진', '성민', '은비', '재현', '예린',
        '태윤', '민지', '시우', '세영', '아린', '진우',
    ],
    # 'korean' : [
    #     '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
    #     '연우', '소윤'
    # ],
}

ENGLISH_NAMES = {
    '지민': 'Jimin',
    '수현': 'Suhyeon',
    '서준': 'Seojun',
    '민서': 'Minseo',
    '도윤': 'Doyun',
    '하늘': 'Haneul',
    '지우': 'Jiwoo',
    '연우': 'Yeonwoo',
    '소윤': 'Soyoon',
    '유진': 'Yujin',
    '성민': 'Seongmin',
    '은비': 'Eunbi',
    '재현': 'Jaehyeon',
    '예린': 'Yerin',
    '태윤': 'Taeyun',
    '민지': 'Minji',
    '시우': 'Siwoo',
    '세영': 'Seyoung',
    '아린': 'Arin',
    '진우': 'Jinwoo',
}

PROHIBITED_WORDS = [
    '시민', '마피아', '경찰', '의사',  # 기본 금칙어
    'citizen', 'mafia', 'police', 'doctor',  # 영어 기본 금칙어
    '살인자', '탐정', '범인', '피해자',  # 게임 관련 단어
    'killer', 'detective', 'criminal', 'victim',  # 영어 관련 단어
    '게임', '승리', '패배', '정답',  # 게임 용어
    'game', 'win', 'lose', 'answer',  # 영어 게임 용어
    'admin', '운영자', '호스트', '관리자',  # 관리 관련 용어
    'admin', 'host', 'moderator',  # 영어 관리 관련 용어
    '죽음', '생존', '투표', '찬성', '반대',  # 게임 진행과 관련된 단어
    'death', 'survival', 'vote', 'yes', 'no',  # 영어 진행 관련 단어
    '123', 'test', '닉네임', '이름', '무작위',  # 일반 금칙어
    'nickname', 'random', 'name', 'test'  # 영어 일반 금칙어
]

class Result(Enum) :
    SUCCESS = 0             # 성공
    TOO_LONG = 1            # 이름이 너무 긺
    CONTAINS_WHITESPACE = 2 # 공백 문자를 포함하고 있음
    INVALID_NAME = 3        # 적합하지 않은 이름임

_chain = None

async def checkName(name: str) -> Result :
    lowerName = name.lower()

    for names in NAMES.values() :
        if lowerName in names :
            return Result.SUCCESS

    if len(lowerName) > 10 :
        return Result.TOO_LONG

    if re.search(r'\s', lowerName) :
        return Result.CONTAINS_WHITESPACE

    for word in PROHIBITED_WORDS :
        if word in lowerName :
            return Result.INVALID_NAME

    _setupChain()

    global _chain
    response = await _chain.ainvoke({
        'name' : lowerName,
    })

    if "false" in response.lower() :
        return Result.SUCCESS
    else :
        return Result.INVALID_NAME

def _setupChain() :
    global _chain
    if _chain != None :
        return

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

    # setup chain
    parser = StrOutputParser()
    _chain = prompt | model | parser
