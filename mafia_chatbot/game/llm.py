if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import json
import os
from typing import Optional, Type, List, Any
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableSerializable
from langchain_core.callbacks import (
    CallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langgraph.prebuilt import create_react_agent

import openai

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.game_info import GameInfo
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo, Role, strToRole, roleToStrDict
from mafia_chatbot.game.strategy import Strategy, Assumption, Estimation, AssumptionType

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

        self._setupHumanMessageAgent(model)

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
        message = await self._ainvokeChain(
            chain=self.humanMessagePreprocessor,
            input={
                'name' : player.info.name,
                'sentence' : message,
            }
        )

        response = await self.humanMessageAgent.ainvoke({'messages': [HumanMessage(message)]})

        for message in reversed(response['messages']) :
            if isinstance(message, ToolMessage) :
                data = json.loads(message.content)

                publicRole: Role = Role.CITIZEN
                assumptionType: AssumptionType = AssumptionType.NORMAL

                police: Player = self.gameState.getPlayerByName(data['police'])
                doctor: Player = self.gameState.getPlayerByName(data['doctor'])

                if police != None and police == player :
                    publicRole = Role.POLICE
                    assumptionType = AssumptionType.TEST_RESULT
                elif doctor != None and doctor == player :
                    publicRole = Role.DOCTOR
                    assumptionType = AssumptionType.HEAL_SUCCESS

                estimations: list[Estimation] = []
                for estimation in data['estimations'] :
                    playerInfo: PlayerInfo = self.gameState.getPlayerInfoByName(estimation['name'])
                    role: Role = strToRole(estimation['role'])
                    if playerInfo != None :
                        if playerInfo == player.info and publicRole == Role.CITIZEN :
                            publicRole = role
                            if role == Role.POLICE :
                                assumptionType = AssumptionType.TEST_RESULT
                            elif role == Role.DOCTOR :
                                assumptionType = AssumptionType.HEAL_SUCCESS
                        else :
                            estimations.append(Estimation(playerInfo, role))

                assumptions: list[Assumption] = [Assumption(estimations, '', assumptionType=assumptionType)]

                if publicRole == Role.CITIZEN :
                    publicRole = player.publicRole
                strategy: Strategy = Strategy(publicRole, assumptions)
                return strategy

        return None

    def _setupDiscussionPromptTemplate(self, gameInfo: GameInfo) -> PromptTemplate :
        templateText = (
            "You are a player participating in a Mafia game. Your name is {my_name}, and your role is {my_role}. {claim_public_role}It is currently the discussion phase, and it is your turn to speak. You must claim that {estimations}. Use the provided ##Conversation Logs## and ##Evidence## as references, or base your claim on your logical reasoning. Keep your statement concise, limited to two sentences, and written in a {tone} tone, written in %(language)s and resembling natural dialogue. Your response should differ from previous statements and introduce variety in phrasing."
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

    def _setupHumanMessageAgent(self, model) :
        # setup preprocessor
        preprocessorTemplate = (
            "If ##sentence## does not contain any first-person pronouns, return it as is without making any changes. If ##sentence## contains any first-person pronouns, replace them with the third-person proper noun \"{name}\" and provide the modified sentence. Do not modify any other parts of the sentence, including other names or the overall sentence structure."
            "\n\n"
            "##sentence##"
            "\n"
            "{name}: {sentence}"
        )
        preprocessorPrompt = PromptTemplate.from_template(preprocessorTemplate)
        preprocessorParser = StrOutputParser()
        self.humanMessagePreprocessor = preprocessorPrompt | model | preprocessorParser

        # setup tools
        nameList = ', '.join(self.gameState.nameList)
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
            police: str = Field(description="The name of the individual who performed an action related to investigation or verification as a police role. If no such role is identified in the context, set to '&none'.")
            doctor: str = Field(description="The name of the individual who performed an action related to healing or saving as a doctor role. If no such role is identified in the context, set to '&none'.")

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
        self.humanMessageAgent = create_react_agent(
            model, tools, state_modifier=systemMessage
        )

    async def _ainvokeChain(self, chain: RunnableSerializable[dict, BaseMessage], input: dict[str, str]) -> BaseMessage :
        try :
            return await chain.ainvoke(input)
        except ValueError as e:
            print(f"[LLM] ValueError: {e}")
            raise e
        except KeyError as e:
            print(f"[LLM] KeyError: Missing key - {e}")
            raise e
        except openai.error.AuthenticationError as e:
            print(f"[LLM] AuthenticationError: {e}")
            raise e
        except openai.error.RateLimitError as e:
            print(f"[LLM] RateLimitError: {e}")
            raise e
        except openai.error.APIError as e:
            print(f"[LLM] APIError: {e}")
            raise e
        except openai.error.Timeout as e:
            print(f"[LLM] TimeoutError: {e}")
            raise e
        except openai.error.InvalidRequestError as e:
            print(f"[LLM] InvalidRequestError: {e}")
            raise e
        # except LangChainError as e:
        #     print(f"[LLM] LangChainError: {e}")
        #     raise e
        except TypeError as e:
            print(f"[LLM] TypeError: {e}")
            raise e
        except Exception as e:
            print(f"[LLM] Unexpected error: {e}")
            raise e
