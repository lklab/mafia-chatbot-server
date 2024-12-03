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
class EstimationInput(BaseModel) :
    name: str = Field(description="The name of the person whose role the human is claiming.")
    role: str = Field(description="The role of the individual with the specified name that the human is claiming.")

class EstimationInputList(BaseModel):
    estimations: List[EstimationInput] = Field(description="A list of estimations.")

class EstimationTool(BaseTool):
    name: str = "EstimationTool"
    description: str = "Call this tool to analyze the human's message."
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
nameList = [
    '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
    '연우', '소윤', '유진', '성민', '은비', '재현', '예린',
    '태윤', '민지', '시우', '세영', '아린', '진우',
]
systemMessageText = (
    "The following text is a statement made by a human participant during a discussion phase in a Mafia game. Your task is to analyze this message and determine which person the user is accusing or identifying as a specific role. The names must match one of those listed in ##list##, taking into account case variations or minor typos. If no sufficiently similar name is found, ignore that part of the message. Similarly, the role must be one of 'citizen', 'police', 'mafia', or 'doctor'. Again, account for case variations or minor typos, and ignore any roles that do not sufficiently match these options. The human participant's name is 도윤. If the message contains first-person pronouns, replace them with 도윤."
    "\n\n"
    "##list##"
    "\n"
    "%(name_list)s"
)
systemMessageText = systemMessageText % {'name_list' : ', '.join(map(lambda name: f'"{name}"', nameList))}
systemMessage = SystemMessage(systemMessageText)

# setup agent
agent_executor = create_react_agent(
    model, tools, state_modifier=systemMessage
)

# execute
name = "도윤"
temp = SystemMessage(f"The human participant's name is {name}. If the message contains first-person pronouns, replace them with {name} and include in estimations.")
response = agent_executor.invoke({'messages': [HumanMessage('나는 경찰이고 예린이가 마피아야.')]})
print(response)
