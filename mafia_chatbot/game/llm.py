if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

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
from langchain_core.messages import SystemMessage, BaseMessage
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt import create_react_agent

import openai

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.game_info import GameInfo
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo, Role, roleToStrDict
from mafia_chatbot.game.strategy import Strategy

class LLM :
    def __init__(self, gameState: GameState) :
        self.gameState = gameState

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

        # setup discussion chain
        discussionPromptTemplate = self._setupDiscussionPromptTemplate(gameState.gameInfo)
        self.discussionChain = discussionPromptTemplate | model

        # setup human message agent
        # self.humanMessageAgent = self._setupHumanMessageAgent(model, self.gameState.nameList)

    async def getDiscussion(self, player: Player, strategy: Strategy) -> str :
        input: dict[str, str] = {
            'my_name' : player.info.name,
            'my_role' : roleToStrDict[player.info.role],
            'claim_public_role' : f"You must claim that your role is {roleToStrDict[player.publicRole]}. " if player.isPublicRoleChanged else "",
            'estimations' : ', '.join(map(lambda e: f"{e.playerInfo.name}'s role is {roleToStrDict[e.role]}", strategy.assumptions[0].estimations)),
            'tone': player.info.tone,
            'conversation_logs' : '\n'.join(self.gameState.conversationLogs),
            'evidence' : strategy.assumptions[0].reason,
        }
        response = await self._ainvokeChain(self.discussionChain, input)
        return response.content

    async def analyzeHumanMessage(self, player: Player, message: str) -> Strategy :
        pass

    def _setupDiscussionPromptTemplate(self, gameInfo: GameInfo) -> PromptTemplate :
        templateText = (
            "You are a player participating in a Mafia game. Your name is {my_name}, and your role is {my_role}. {claim_public_role}It is currently the discussion phase, and it is your turn to speak. You must claim that {estimations}. Use the provided ##Conversation Logs## and ##Evidence## as references, or base your claim on your logical reasoning. Your statement should be concise, limited to two sentences, and written in a {tone} conversational style. Your response should differ from previous statements and introduce variety in phrasing. Write your statement in %(language)s."
            "\n\n"
            "##Conversation Logs##"
            "\n"
            "{conversation_logs}"
            "\n\n"
            "##Evidence##"
            "\n"
            "{evidence}"
        )
        templateText = templateText % {'language' : gameInfo.language}
        promptTemplate = PromptTemplate.from_template(templateText)
        return promptTemplate

    async def _ainvokeChain(self, chain: RunnableSerializable[dict, BaseMessage], input: dict[str, str]) -> BaseMessage :
        try :
            return await chain.ainvoke(input)
        except ValueError as e:
            print(f"[LLM] ValueError: {e}")
        except KeyError as e:
            print(f"[LLM] KeyError: Missing key - {e}")
        except openai.error.AuthenticationError as e:
            print(f"[LLM] AuthenticationError: {e}")
        except openai.error.RateLimitError as e:
            print(f"[LLM] RateLimitError: {e}")
        except openai.error.APIError as e:
            print(f"[LLM] APIError: {e}")
        except openai.error.Timeout as e:
            print(f"[LLM] TimeoutError: {e}")
        except openai.error.InvalidRequestError as e:
            print(f"[LLM] InvalidRequestError: {e}")
        # except LangChainError as e:
        #     print(f"[LLM] LangChainError: {e}")
        except TypeError as e:
            print(f"[LLM] TypeError: {e}")
        except Exception as e:
            print(f"[LLM] Unexpected error: {e}")

    def analyzeHumanMessage(self, player: Player, message: str) -> Strategy :
        # response = self.humanMessageAgent.invoke({'messages': [('user', message)]})

        # for message in reversed(response['messages']) :
        #     if isinstance(message, ToolMessage) :
        #         data = json.loads(message.content)

        #         publicRole: Role = None
        #         if 'role' in data :
        #             publicRole = strToRole(data['role'])
        #         if publicRole == None :
        #             publicRole = player.publicRole

        #         estimations: list[Estimation] = []
        #         for estimation in data['estimations'] :
        #             playerInfo: PlayerInfo = self.gameState.getPlayerInfoByName(estimation['name'])
        #             role: Role = strToRole(estimation['role'])
        #             if playerInfo != None and role != None :
        #                 estimations.append(Estimation(playerInfo, role))

        #         assumptions: list[Assumption] = [Assumption(estimations, '')]

        #         strategy: Strategy = Strategy(publicRole, assumptions)
        #         return strategy

        return None

    def _setupHumanMessageAgent(self, model) :
        # setup tools
        class EstimationInput(BaseModel) :
            name: str = Field(description="The name of the person whose role the human is claiming.")
            role: str = Field(description="The role of the individual with the specified name that the human is claiming.")

        class EstimationTool(BaseTool):
            name: str = "EstimationTool"
            description: str = "Call this tool to analyze the human's message."
            args_schema: Type[BaseModel] = EstimationInput
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
            "The following text is a statement made by a human participant during a discussion phase in a Mafia game. Your task is to analyze this message and determine which person the user is accusing or identifying as a specific role. The names must match one of those listed in ##list##, taking into account case variations or minor typos. If no sufficiently similar name is found, ignore that part of the message. Similarly, the role must be one of 'citizen', 'police', 'mafia', or 'doctor'. Again, account for case variations or minor typos, and ignore any roles that do not sufficiently match these options."
            "\n\n"
            "##list##"
            "\n"
            "%(name_list)s"
        )
        systemMessageText = systemMessageText % {'name_list' : ', '.join(map(lambda name: f'"{name}"', self.gameState.nameList))}
        systemMessage = SystemMessage(systemMessageText)

        # setup agent
        agent_executor = create_react_agent(
            model, tools, state_modifier=systemMessage
        )

        return agent_executor

        class EstimationInput(BaseModel) :
            name: str = Field(description="The name of the person whose role the speaker is claiming.")
            role: str = Field(description="The role of the individual with the specified name that the speaker is claiming.")

        class ClaimInput(BaseModel) :
            role: str = Field(description="It must be the speaker's role, not someone else's role.")
            estimations: list[EstimationInput] = Field(description="The roles the speaker is claiming for other people.",)

        class ClaimInputWithoutSpeakerRole(BaseModel) :
            estimations: list[EstimationInput] = Field(description="The roles the speaker is claiming for other people.",)

        class ClaimTool(BaseTool):
            name: str = "ClaimTool"
            description: str = "Call this tool to analyze the speaker's message. If the speaker claimed their own role, call this tool. For example, a statement like 'My role is citizen' is considered a claim of their own role."
            args_schema: Type[BaseModel] = ClaimInput
            return_direct: bool = True

            def _run(
                self, role: str, estimations: list[EstimationInput], run_manager: Optional[CallbackManagerForToolRun] = None
            ) -> dict:
                data = {}
                data['role'] = role
                data['estimations'] = []
                for estimation in estimations :
                    data['estimations'].append({
                        'name': estimation.name,
                        'role': estimation.role
                    })
                return data

        class ClaimToolWithoutSpeakerRole(BaseTool):
            name: str = "ClaimToolWithoutSpeakerRole"
            description: str = "Call this tool to analyze the speaker's message. If the speaker did not claim their own role but only asserted the roles of others, call this tool instead of ClaimTool."
            args_schema: Type[BaseModel] = ClaimInputWithoutSpeakerRole
            return_direct: bool = True

            def _run(
                self, estimations: list[EstimationInput], run_manager: Optional[CallbackManagerForToolRun] = None
            ) -> dict:
                data = {}
                data['estimations'] = []
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

        tools = [ClaimTool(), ClaimToolWithoutSpeakerRole(), fallbackTool]

        system_message = SystemMessage(content=f"The following message is a statement made during a game of Mafia. You need to analyze this message to determine what the speaker is claiming and call the appropriate tool. The names should be the closest match from {', '.join(map(lambda name: f'\'{name}\'', nameList))}. The roles should be the closest match from 'citizen', 'police', 'mafia', 'doctor'. If the names or roles differ significantly from the given strings or are not present in the message, input the string 'none'.")

        agent_executor = create_react_agent(
            model, tools, state_modifier=system_message
        )

        return agent_executor

if __name__ == "__main__" :
    class Person :
        def __init__(self, name, color) :
            self.name = name
            self.color = color

    prompt1 = PromptTemplate.from_template('My name is {name} and I like {prompt2}')
    # prompt2 = PromptTemplate.from_template('{color} Table.')

    def inputPreprocessor(input) :
        return {
            'name': input['person'].name,
            'color': input['person'].color,
        }

    def getMyPrompt(input) :
        print('ccc')
        prompt2 = PromptTemplate.from_template('{color} Table.')
        return prompt2.invoke(input).text

    print('aaa')
    prompt = (
        RunnableLambda(inputPreprocessor)
        | RunnablePassthrough.assign(prompt2=RunnableLambda(getMyPrompt))
        | prompt1
    )

    print('bbb')
    print(prompt.invoke({'person': Person('Broccoli', 'yellow')}))
