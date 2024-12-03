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

prompt_template = PromptTemplate(
    input_variables=["message", "name_list", "user_name"],
    template=("""
메시지를 분석하고 아래 JSON 형식으로 결과를 반환하세요:
[{{"name": "<이름>", "role": "<역할>"}}]

규칙:
- 이름은 제공된 이름 리스트에서 선택하세요: {name_list}.
- 역할은 다음 중 하나여야 합니다: 'citizen', 'police', 'mafia', 'doctor'.
- 메시지에 "나" 또는 1인칭 대명사가 나오면 그것을 {user_name}으로 간주하고 해당 역할을 매핑하세요.
- 매칭되지 않는 이름이나 역할은 무시하세요.
- 만약 마피아 게임과 상관 없는 메시지라면 비어있는 JSON 배열을 반환하세요.

분석할 메시지: "{message}"
    """)
)

# setup chain
chain = prompt_template | model | parser

message = "나는 경찰이고 예린이가 마피아야."
name_list = ["예린", "도윤", "지훈", "민서"]
user_name = "도윤"

result = chain.invoke({
    'message' : "오늘 날씨가 좋아",
    'name_list' : ', '.join(["예린", "도윤", "지훈", "민서"]),
    'user_name' : "도윤",
})
print(result)

async def ainvoke(country: str) :
    result = await chain.ainvoke({'country' : country})
    print(result)

# asyncio.run(ainvoke('대한민국'))
