import json
import os
from typing import Optional, Type, List
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
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
    # model="gpt-4-turbo",
    temperature=0.1,
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
    police: str = Field(description="The name of the individual who performed an action related to investigation or verification as a police role. If no such role is identified in the context, set to 'none'.")
    doctor: str = Field(description="The name of the individual who performed an action related to healing or saving as a doctor role. If no such role is identified in the context, set to 'none'.")

class EstimationTool(BaseTool):
    name: str = "EstimationTool"
    description: str = estimationToolDescription
    args_schema: Type[BaseModel] = EstimationInputList
    return_direct: bool = True

    def _run(self, estimations: List[EstimationInput], police: str, doctor: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> dict:
        data = {
            'estimations': [],
            'police': police,
            'doctor': doctor,
        }
        for estimation in estimations :
            data['estimations'].append({
                'name': estimation.name,
                'role': estimation.role
            })
        return data

def fallback() -> str :
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
    "he following message is a conversation log from a Mafia game, and the final message is a statement made by a human participant. Your task is to analyze the final message and invoke the appropriate tools."
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


# template = (
#     "If ##sentence## does not contain any first-person pronouns, return it as is without making any changes. If ##sentence## contains any first-person pronouns, replace them with the third-person proper noun \"{name}\" and provide the modified sentence. Do not modify any other parts of the sentence, including other names or the overall sentence structure."
#     "\n\n"
#     "##sentence##"
#     "\n"
#     "{sentence}"
# )
# prompt = PromptTemplate.from_template(template)
# parser = StrOutputParser()
# chain = prompt | model | parser

# response = chain.invoke({
#     'name' : "민지",
#     # 'sentence' : "민지: 나는 시우가 마피아라고 확신해. 왜냐면 내가 조사했거든",
#     # 'sentence' : "민지: 나도 시우와 같은 생각이야",
#     'sentence' : "민지: 나는 마피아가 아니야",
# })
# print(f'[1]\n{response}')

template = (
    "##sentence## is a statement made by a human player during the discussion phase of a Mafia game. Your task is to determine whether the sentence clearly indicates who the human player suspects of having a specific role based solely on its content. The roles can include Citizen, Mafia, Police, or Doctor. If the sentence explicitly identifies a person and their suspected role, or explicitly claims that a person does NOT have a specific role, respond with \"true\"; otherwise, respond with \"false\""
    "\n\n"
    "##sentence##"
    "\n"
    "{sentence}"
)
prompt = PromptTemplate.from_template(template)
parser = StrOutputParser()
chain = prompt | model | parser

response = chain.invoke({
    # 'name' : "민지",
    'sentence' : "민지: 나는 시우의 의견에 동의해",
})
print(f'[2]\n{response.lower()}')

# template = (
#     "Given a ##conversation history## and the latest statement ##sentence##, which is a remark made during the discussion phase of a Mafia game and might reference context from the ##conversation history##, rewrite ##sentence## into a standalone statement that clearly indicates who the speaker thinks has which role. If ##sentence## agrees or disagrees with a previous statement in the ##conversation history##, rewrite it to logically reflect what the speaker believes about the roles based on that agreement or disagreement. The rewritten statement should be specific and complete, without requiring any reference to other parts of the conversation. Do NOT interpret or analyze the statement; simply rewrite it if necessary, or return it as is if already standalone."
#     "\n\n"
#     "##conversation history##"
#     "\n"
#     "{history}"
#     "\n\n"
#     "##sentence##"
#     "\n"
#     "{sentence}"
# )
# prompt = PromptTemplate.from_template(template)
# parser = StrOutputParser()
# chain = prompt | model | parser

# response = chain.invoke({
#     'history' : "은비: 나는 시우가 마피인 것 같아.\n시우: 나는 은비가 마피아라고 생각해",
#     'sentence' : "민지: 나는 은비의 의견에 동의하지 않아",
# })
# print(f'[2]\n{response}')

# response = agent_executor.invoke({'messages': [
#     HumanMessage('은비: 나는 시우가 마피인 것 같아.'),
#     HumanMessage('시우: 나는 은비가 마피아라고 생각해'),
#     HumanMessage('민지: 나는 은비의 의견에 동의하지 않아'),
# ]})
# print(f'[3]\n{response}')







# nameList = ', '.join([
#     '지민', '수현', '서준', '민서', '도윤', '하늘', '지우',
#     '연우', '소윤', '유진', '성민', '은비', '재현', '예린',
#     '태윤', '민지', '시우', '세영', '아린', '진우',
# ])

# systemMessageTemplate = (
#     "Below is a conversation snippet from a Mafia game. Generate the name of the participant who will respond to the last message and their response message in JSON format. The name must be one from the {nameList}. You can freely and creatively write the content of the response message, but it must be something plausible within the context of a Mafia game and must not contradict the participant's previous claims. For the JSON format, provide only the JSON itself as the output, without enclosing it in code blocks or additional text."
#     "\n\n"
#     "##JSON format##"
#     "\n"
#     '\"{{"name":"", "message":""}}\"'
# )
# prompt = ChatPromptTemplate.from_messages(
#     [
#         ('system', systemMessageTemplate),
#         MessagesPlaceholder(variable_name="messages"),
#     ]
# )
# parser = StrOutputParser()
# chain = prompt | model | parser

# response = chain.invoke({
#     'nameList' : nameList,
#     'messages' : [
#         HumanMessage(content="은비: 나는 시우가 마피인 것 같아"),
#         HumanMessage(content="시우: 나는 은비가 마피아라고 생각해"),
#         HumanMessage(content="민지: 오늘은 날씨가 좋네"),
#     ],
# })
# print(f'{response}')









# response = chain.invoke({
#     'history' : "진우: 날씨가 좋은데?\n은비: 나는 시우가 마피인 것 같아.\n시우: 나는 은비가 마피아라고 생각해\n민지: 나는 진우가 마피아라고 생각해\n진우: 민지야, 왜 그렇게 생각해? 진우가 마피아일 리가 없어.",
#     'message' : "민지: 진우야 왜 자신을 3인칭으로 지칭해?",
# })
# print(f'{response}')

# template = (
#     "Respond with \"true\" if ##message## is a question; otherwise, respond with \"false\"."
#     "\n\n"
#     "##message##"
#     "\n"
#     "{message}"
# )
# prompt = PromptTemplate.from_template(template)
# parser = StrOutputParser()
# chain = prompt | model | parser

# response = chain.invoke({
#     "message" : "민지: 왜 그렇게 생각하는거야",
# })
# print(response)
