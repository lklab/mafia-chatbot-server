import json
import os
from typing import Optional, Type, List
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda, RunnableSerializable
from langchain_core.callbacks import (
    CallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt import create_react_agent
from langchain.tools import Tool
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

# setup tools
name = '도윤'
nameList = ', '.join([
    '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
    '연우', '소윤', '유진', '성민', '은비', '재현', '예린',
    '태윤', '민지', '시우', '세영', '아린', '진우',
])
# name = 'Evelyn'
# nameList = ', '.join([
#     'Oliver', 'Emma', 'Noah', 'Ava', 'Liam', 'Sophia', 'Mason', 'Isabella',
#     'James', 'Mia', 'Benjamin', 'Amelia', 'Ethan', 'Harper', 'Lucas',
#     'Charlotte', 'Henry', 'Evelyn', 'Jack', 'Grace',
# ])

estimationToolDescription = (
    "If a human participant claims someone to be a specific role, invoke this tool. The name must match one from the ##list##, and the role must be one of 'citizen,' 'police,' 'mafia,' or 'doctor.' If there is no exact match for the name or role, attempt to find the closest match considering case sensitivity or typos. If no sufficiently similar match exists, ignore the statement."
    "\n\n"
    "##list##"
    "\n"
    f"{nameList}"
)

class EstimationInput(BaseModel) :
    name: str = Field(description="The name of the person whose role the human is claiming.")
    role: str = Field(description="The role (must be in English) of the individual with the specified name that the human is claiming.")

class EstimationInputList(BaseModel):
    estimations: List[EstimationInput] = Field(description="A list of estimations.")

class EstimationTool(BaseTool):
    name: str = "EstimationTool"
    description: str = estimationToolDescription
    args_schema: Type[BaseModel] = EstimationInputList
    return_direct: bool = True

    def _run(self, estimations: List[EstimationInput], run_manager: Optional[CallbackManagerForToolRun] = None) -> dict:
        data = {'estimations': []}
        for estimation in estimations :
            data['estimations'].append({
                'name': estimation.name,
                'role': estimation.role
            })
        return data

def fallback() -> str:
    print('fallback')
    return 'fallback'

fallbackTool = StructuredTool.from_function(
    func=fallback,
    name="Fallback",
    description="If the speaker's message is unrelated to the Mafia game, call this tool.",
    return_direct=True,
)

tools = [EstimationTool(), fallbackTool]

# setup system message
systemMessageText = (
    "The following message is a statement made by a human participant during the discussion phase of a mafia game. Your task is to analyze this message and invoke the appropriate tools."
)
systemMessage = SystemMessage(systemMessageText)

# setup agent
agent_executor = create_react_agent(
    model, tools, state_modifier=systemMessage
)

# execute
# response = agent_executor.invoke({'messages': [HumanMessage('나는 경찰이고 예린이가 마피아야.')]})
# print(response)

# response = agent_executor.invoke({'messages': [HumanMessage('I am a police and Noah is a bad man.')]})
# print(response)


template = (
    "If ##sentence## does not contain any first-person pronouns, return it as is without making any changes. If ##sentence## contains any first-person pronouns, replace them with the third-person proper noun \"{name}\" and provide the modified sentence. Do not modify any other parts of the sentence, including other names or the overall sentence structure."
    # "If ##sentence## contains any first-person pronouns?"
    "\n\n"
    "##sentence##"
    "\n"
    "{sentence}"
)
prompt = PromptTemplate.from_template(template)
parser = StrOutputParser()
chain = prompt | model | parser

response = chain.invoke({
    'name' : "경현",
    'sentence' : "경현: 내 생각에 시우가 마피아라고 생각해.",
})
print(f'[1]\n{response}')

response = agent_executor.invoke({'messages': [HumanMessage(response)]})
print(f'[2]\n{response}')
