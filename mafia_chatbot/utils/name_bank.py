from enum import Enum
import re
import json
import os
import random
import sqlite3

from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

NAMES: dict[str, list[str]] = None
ENGLISH_NAMES: dict[str, dict[str, str]] = None
PROHIBITED_WORDS: list[str] = None
prohibitedWordsDB: 'ProhibitedWordsDB' = None

def initialize() :
    global NAMES
    global ENGLISH_NAMES
    global PROHIBITED_WORDS
    global prohibitedWordsDB

    NAMES = {}
    ENGLISH_NAMES = {}
    PROHIBITED_WORDS = []
    prohibitedWordsDB = ProhibitedWordsDB()

    with open(os.path.join('data', 'names.json'), encoding='utf-8') as f :
        data = json.load(f)

    for language, langData in data.items() :
        names: list[str] = []
        englishNames: dict[str, str] = {}
        NAMES[language] = names
        ENGLISH_NAMES[language] = englishNames

        for name in langData['names'] :
            names.append(name['name'])
            englishNames[name['name']] = name['en']

        for prohibited in langData['prohibiteds'] :
            PROHIBITED_WORDS.append(prohibited)

def isSupportedLanguage(language: str) -> bool :
    global NAMES
    return language in NAMES

def getCopyAndShuffleNames(language: str) -> list[str] :
    global NAMES

    if language in NAMES :
        names = NAMES[language].copy()
    else :
        names = NAMES['english'].copy()

    random.shuffle(names)
    return names

class EnglishNameMaker :
    def __init__(self, language: str) :
        self.enNameDict: dict[str, str] = ENGLISH_NAMES[language]
        self.enNames: list[str] = NAMES['english']
        self.enNameIndex: int = 0
        self.enNameSet: set[str] = set(self.enNameDict.values())

    def getEnglishName(self, name: str) -> str :
        # 사전 정의된 이름인 경우
        if name in self.enNameDict :
            enName: str = self.enNameDict[name]

        # 커스텀 이름인 경우 기존 이름과 상관 없이 영어 이름을 할당
        else :
            # 이름 데이터는 50개가 넘는데, 플레이어는 최대 10명이므로 인덱스 검사는 하지 않음
            enName: str = self.enNames[self.enNameIndex]
            while enName in self.enNameSet :
                self.enNameIndex += 1
                enName: str = self.enNames[self.enNameIndex]
            self.enNameIndex += 1

        return enName

class Result(Enum) :
    SUCCESS = 0             # 성공
    TOO_SHORT = 1           # 이름이 너무 짧음
    TOO_LONG = 2            # 이름이 너무 긺
    CONTAINS_WHITESPACE = 3 # 공백 문자를 포함하고 있음
    INVALID_NAME = 4        # 적합하지 않은 이름임

_chain = None

async def checkName(name: str) -> Result :
    lowerName = name.lower()

    for recommends in NAMES.values() :
        for recommend in recommends :
            if lowerName == recommend.lower() :
                return Result.SUCCESS

    if len(lowerName) <= 1 :
        return Result.TOO_SHORT

    if len(lowerName) > 10 :
        return Result.TOO_LONG

    if re.search(r'\s', lowerName) :
        return Result.CONTAINS_WHITESPACE

    for word in PROHIBITED_WORDS :
        if word in lowerName :
            return Result.INVALID_NAME

    if prohibitedWordsDB.is_prohibited(lowerName) :
        return Result.INVALID_NAME

    _setupChain()

    global _chain
    response = await _chain.ainvoke({
        'name' : lowerName,
    })

    if "false" in response.lower() :
        return Result.SUCCESS
    else :
        prohibitedWordsDB.add_word(lowerName)
        return Result.INVALID_NAME

def _setupChain() :
    global _chain
    if _chain != None :
        return

    # load API key
    with open('config/apikeys.json') as f:
        keys = json.load(f)

    os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
    os.environ["GOOGLE_API_KEY"] = keys['GOOGLE_API_KEY']
    os.environ["ANTHROPIC_API_KEY"] = keys['ANTHROPIC_API_KEY']

    if 'LANGCHAIN_API_KEY' in keys :
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

    # setup model
    model = ChatAnthropic(
        model="claude-3-5-haiku-20241022",
        temperature=0.2,
    )

    # setup prompt
    template = (
        "You are tasked with evaluating names submitted by users for use in a Mafia game to determine if they are suitable. If the ##name## is any of the following:"
        "\n"
        "A word that is generally not recognized as a name (e.g., \"unknown,\" \"no\")."
        "\n"
        "A term commonly used in Mafia games (e.g., \"citizen,\" \"mafia,\" \"police,\" \"doctor,\" \"vote,\" \"execution\")."
        "\n"
        "A personal pronoun (e.g., \"I,\" \"you,\" \"we\")."
        "\n"
        "A word that is offensive, profane, or discriminatory."
        "\n"
        "Return \"true\". Otherwise, return \"false\". Return only \"true\" or \"false\". Do not include any explanations or additional text."
        "\n\n"
        "##name##"
        "\n"
        "{name}"
    )
    prompt = PromptTemplate.from_template(template)

    # setup chain
    parser = StrOutputParser()
    _chain = prompt | model | parser

class ProhibitedWordsDB:
    def __init__(self):
        os.makedirs('sqlite3', exist_ok=True)
        self.db_name = 'sqlite3/prohibited_words.db'
        self._initialize_db()

    def _initialize_db(self):
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS prohibited_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT UNIQUE NOT NULL
                )
                """
            )
            conn.commit()

    def add_word(self, word: str):
        """금칙어 추가 (중복 금지)"""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO prohibited_words (word) VALUES (?)", (word,))
                conn.commit()
        except sqlite3.IntegrityError:
            pass  # 이미 존재하는 경우 무시

    def is_prohibited(self, word: str) -> bool:
        """특정 단어가 금칙어인지 확인"""
        with sqlite3.connect(self.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM prohibited_words WHERE word = ?", (word,))
            return cursor.fetchone() is not None
