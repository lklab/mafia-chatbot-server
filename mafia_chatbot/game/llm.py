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
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic

from langchain_core.prompts import PromptTemplate, ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableSerializable
from langchain_core.callbacks import (
    CallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.messages import SystemMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langgraph.prebuilt import create_react_agent

from mafia_chatbot.game.game_state import GameState
from mafia_chatbot.game.game_info import GameInfo
from mafia_chatbot.game.player import Player
from mafia_chatbot.game.player_info import PlayerInfo, Role, strToRole, roleToStrDict
from mafia_chatbot.game.strategy import Strategy, Assumption, Estimation, AssumptionType
from mafia_chatbot.game.game_logger import GameLogger, TAG

class LLM :
    def __init__(self, gameState: GameState) :
        self.gameState = gameState
        self.logger: GameLogger = gameState.logger

        # load API key
        with open('config/apikeys.json') as f:
            keys = json.load(f)

        os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
        os.environ["GOOGLE_API_KEY"] = keys['GOOGLE_API_KEY']
        os.environ["ANTHROPIC_API_KEY"] = keys['ANTHROPIC_API_KEY']

        if 'LANGCHAIN_API_KEY' in keys :
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

        # setup chains and agents
        self._setupDiscussionChain(gameState.gameInfo)
        self._setupTranslateChain()
        self._setupRemoveFirstPersonChain()
        self._setupHumanMessageAgent()
        self._setupCheckClaimsMafiaChain()
        self._setupCheckQuestionChain()
        self._setupGenerateResponseChain(gameState.gameInfo)
        self._setupGenerateQuestionChain(gameState.gameInfo)
        self._setupGenerateNormalDiscussionChain(gameState.gameInfo)

    async def getDiscussion(self, player: Player, strategy: Strategy, conversationLogsCount: int = 5) -> str :
        self.logger.log(TAG.LLM, f'{player.info.name}: getDiscussion input: {strategy}')

        publicRole, _ = player.getChangeRole(strategy.publicRole)
        isPublicRoleChanged: bool = player.publicRole != publicRole

        publicRoleStrategy: str = ""
        if isPublicRoleChanged :
            publicRoleStrategy = f"You must claim that your role is {roleToStrDict[publicRole]}."
        elif player.info.role != Role.CITIZEN and publicRole == Role.CITIZEN :
            publicRoleStrategy = "You must not disclose your role."

        input: dict[str, str] = {
            'my_name' : player.info.name,
            'my_role' : roleToStrDict[player.info.role],
            'public_role_strategy' : publicRoleStrategy,
            'estimations' : ', '.join(map(lambda e: f"{e.playerInfo.name}'s role is {roleToStrDict[e.role]}", strategy.assumptions[0].estimations)),
            'tone': player.info.tone,
            'conversation_logs' : '\n'.join(self.gameState.getRecentConversationLogs(conversationLogsCount)),
            'evidence' : strategy.assumptions[0].reason,
        }

        response = await self._ainvokeChain(self.discussionChain, input)
        self.logger.log(TAG.LLM, f'{player.info.name}: getDiscussion response: {response}')
        return response.content

    async def checkContainsEstimation(self, message: str) -> bool : # not used
        self.logger.log(TAG.LLM, f'checkContainsEstimation input: {message}')

        response: str = await self._ainvokeChain(
            chain=self.checkContainsEstimationChain,
            input={
                'sentence' : message,
            }
        )

        self.logger.log(TAG.LLM, f'checkContainsEstimation response: {response}')
        return "true" in response.lower()

    async def analyzeHumanMessage(self, player: Player, message: str) -> Strategy :
        self.logger.log(TAG.LLM, f'{player.info.name}: analyzeHumanMessage input: {message}')

        if self.gameState.gameInfo.language != 'english' :
            message = await self._ainvokeChain(
                chain=self.translateChain,
                input={
                    'sentence' : message,
                }
            )

            if not message or message == '""' :
                return None

        message = await self._ainvokeChain(
            chain=self.removeFirstPersonChain,
            input={
                'name' : player.info.englishName,
                'sentence' : message,
            }
        )

        response = await self.humanMessageAgent.ainvoke({'messages': [HumanMessage(message)]})
        self.logger.log(TAG.LLM, f'analyzeHumanMessage response: {response}')

        strategy: Strategy = None

        for llmMessage in reversed(response['messages']) :
            if isinstance(llmMessage, ToolMessage) :
                try :
                    data = json.loads(llmMessage.content)

                    publicRole: Role = Role.CITIZEN
                    assumptionType: AssumptionType = AssumptionType.NORMAL

                    police: Player = self.gameState.getPlayerByEnglishName(data['police'])
                    doctor: Player = self.gameState.getPlayerByEnglishName(data['doctor'])

                    if police != None and police == player :
                        publicRole = Role.POLICE
                        assumptionType = AssumptionType.TEST_RESULT
                    elif doctor != None and doctor == player :
                        publicRole = Role.DOCTOR
                        assumptionType = AssumptionType.HEAL_SUCCESS

                    estimations: list[Estimation] = []
                    for estimation in data['estimations'] :
                        playerInfo: PlayerInfo = self.gameState.getPlayerInfoByEnglishName(estimation['name'])
                        role: Role = strToRole(estimation['role'])
                        if role == None :
                            role = Role.CITIZEN

                        if playerInfo != None :
                            if playerInfo == player.info and publicRole == Role.CITIZEN :
                                publicRole = role
                                if role == Role.POLICE :
                                    assumptionType = AssumptionType.TEST_RESULT
                                elif role == Role.DOCTOR :
                                    assumptionType = AssumptionType.HEAL_SUCCESS
                            elif playerInfo != player.info :
                                estimations.append(Estimation(playerInfo, role))

                    assumptions: list[Assumption] = [Assumption(estimations, '', assumptionType=assumptionType)]

                    if publicRole == Role.CITIZEN :
                        publicRole = player.publicRole
                    strategy = Strategy(publicRole, assumptions)
                    break

                except :
                    continue

        # 플레이어가 자신이 마피아라고 주장한 것이 맞는지 다시 확인
        if strategy != None and player.publicRole != Role.MAFIA and strategy.publicRole == Role.MAFIA :
            response = await self._ainvokeChain(
                chain=self.checkClaimsMafiaChain,
                input={
                    'name' : player.info.englishName,
                    'sentence' : message,
                }
            )

            if "false" in response.lower() :
                strategy.publicRole = player.publicRole

        return strategy

    async def isMessageQuestion(self, message: str) -> bool :
        self.logger.log(TAG.LLM, f'isMessageQuestion input: {message}')

        response: str = await self._ainvokeChain(
            chain=self.checkQuestionChain,
            input={
                'message' : message,
            }
        )

        self.logger.log(TAG.LLM, f'isMessageQuestion response: {response}')
        return "true" in response.lower()

    async def generateResponse(self, speaker: Player, conversation: list[str]) -> tuple[Player, str] :
        self.logger.log(TAG.LLM, f'{speaker.info.name}: generateResponse')

        # setup input
        nameList: str = ', '.join(map(lambda p: p.info.name, filter(lambda p: p != speaker, self.gameState.players)))
        self.logger.log(TAG.LLM, f'{speaker.info.name}: generateResponse name list: {nameList}')

        messages = []
        for message in conversation :
            messages.append(HumanMessage(content=message))

        # call chain
        jsonData: str = await self._ainvokeChain(
            chain=self.generateResponseChain,
            input={
                'nameList' : nameList,
                'lastMessage': conversation[-1],
                'messages' : messages,
            }
        )
        self.logger.log(TAG.LLM, f'{speaker.info.name}: generateResponse response: {jsonData}')

        # parse response
        try :
            data = json.loads(jsonData)
            name: str = data['name']
            message: str = data['message']
        except json.JSONDecodeError as e :
            self.logger.log(TAG.ERROR, f'[LLM] generateResponse JSONDecodeError: {e}')
            return (None, None)
        except Exception as e :
            self.logger.log(TAG.ERROR, f'[LLM] generateResponse Exception: {e}')
            return (None, None)

        # get respondent player
        respondent: Player = self.gameState.getPlayerByName(name)
        if respondent == None or respondent.info.isHuman or respondent == speaker :
            return (None, None)

        return (respondent, message)

    async def generateQuestion(self, speaker: Player, target: Player, conversation: list[str]) -> str :
        self.logger.log(TAG.LLM, f'{speaker.info.name}: generateQuestion, target: {target.info.name}')

        messages = []
        for message in conversation :
            messages.append(HumanMessage(content=message))

        return await self._ainvokeChain(
            chain=self.generateQuestionChain,
            input={
                'my_name' : speaker.info.name,
                'name' : target.info.name,
                'tone' : speaker.info.tone,
                'messages' : messages,
            }
        )

    async def generateNormalDiscussion(self, speaker: Player, conversation: list[str]) -> str :
        self.logger.log(TAG.LLM, f'{speaker.info.name}: generateNormalDiscussion')

        messages = []
        for message in conversation :
            messages.append(HumanMessage(content=message))

        return await self._ainvokeChain(
            chain=self.generateNormalDiscussionChain,
            input={
                'my_name' : speaker.info.name,
                'tone' : speaker.info.tone,
                'otherParticipants' : ', '.join(map(lambda p : p.info.name, filter(lambda p : p != speaker, self.gameState.players))),
                'messages' : messages,
            }
        )

    def _setupDiscussionChain(self, gameInfo: GameInfo) :
        # setup model
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.7,
        )

        # setup prompt
        template = (
            "You are a player participating in a Mafia game. Your name is {my_name}, and your role is {my_role}. It is currently the discussion phase, and it is your turn to speak. {public_role_strategy} You must claim that {estimations}. Use the provided ##Conversation Logs## and ##Evidence## as references, or base your claim on your logical reasoning. Keep your statement concise, limited to two sentences, and written in a {tone} tone, written in %(language)s and resembling natural dialogue.%(dont_tranlate)s Your response should differ from previous statements and introduce variety in phrasing."
            "\n\n"
            "##Conversation Logs##"
            "\n"
            "{conversation_logs}"
            "\n\n"
            "##Evidence##"
            "\n"
            "{evidence}"
        )
        template = template % {
            'language' : gameInfo.language,
            'dont_tranlate' : ' Do not translate into english.' if gameInfo.language != 'english' else '',
        }
        prompt = PromptTemplate.from_template(template)

        # setup chain
        self.discussionChain = prompt | model

    def _setupTranslateChain(self) :
        # setup model
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.1,
        )

        names = '\n'.join(map(lambda p: f'"{p.info.name}": "{p.info.englishName}"', self.gameState.players))
        template = (
            f"Translate the following ##sentence## into English without altering its original meaning. Use the specified words from ##names## for proper nouns and the terms from ##terms## to ensure consistent vocabulary for similar or identical meanings. If ##sentence## does not contain meaningful content (e.g., numbers, empty strings, or non-sentential fragments), return an empty string instead."
            "\n\n"
            "##sentence##"
            "\n"
            "{sentence}"
            "\n\n"
            "##names##"
            "\n"
            f"{names}"
            "\n\n"
            "##terms##"
            "\n"
            "citizen, mafia, police, doctor, vote, execution, assassination, investigation, healing"
        )
        prompt = PromptTemplate.from_template(template)

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.translateChain = prompt | model | parser

    def _setupRemoveFirstPersonChain(self) :
        # setup model
        model = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            temperature=0.1,
        )

        # setup prompt
        template = (
            "If ##sentence## contains any first-person pronouns (e.g., I, me, my, mine, myself), replace them with \"{name}\" and provide the modified sentence. Do not replace second-person pronouns (e.g., you, your) or third-person pronouns (e.g., he, she, it, they, their, them, himself, herself), nor any other words that are not first-person pronouns. Do not modify any other parts of the sentence, including other names or the overall sentence structure. Output only the modified sentence. Do not include any explanations or additional text."
            "\n\n"
            "Example 1 (First-person):"
            "\n"
            "Input: \"I think my idea will work better than mine.\""
            "\n"
            "Output: \"{name} think {name}'s idea will work better than {name}'s.\""
            "\n\n"
            "Example 2 (Third-person):"
            "\n"
            "Input: \"She thinks her idea is better than mine.\""
            "\n"
            "Output: \"She thinks her idea is better than {name}'s.\""
            "\n\n"
            "##sentence##"
            "\n"
            "{sentence}"
        )
        prompt = PromptTemplate.from_template(template)

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.removeFirstPersonChain = prompt | model | parser

    def _setupHumanMessageAgent(self) :
        # setup model
        model = ChatOpenAI(
            model="gpt-3.5-turbo",
            temperature=0.1,
        )

        # setup tools
        nameList = ', '.join(self.gameState.englishNameList)
        estimationToolDescription = (
            "If a human participant claims someone to be a specific role, invoke this tool. The name must match one from the ##list##, and the role must be one of 'citizen,' 'police,' 'mafia,' or 'doctor.' Treat cases where someone is suspected as equivalent to them being claimed as a mafia. If there is no exact match for the name or role, attempt to find the closest match considering case sensitivity or typos. If no sufficiently similar match exists, ignore the statement."
            "\n\n"
            "##list##"
            "\n"
            f"{nameList}"
        )

        class EstimationInput(BaseModel) :
            name: str = Field(description="The name of the person whose role the human is claiming.")
            role: str = Field(description="The role of the individual with the specified name that the human is claiming.")

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

        def fallback() -> str :
            self.logger.log(TAG.ERROR, f'[LLM] fallbacked')
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
            "The following message is a statement made by a human participant during the discussion phase of a mafia game. Your task is to analyze this message and invoke the appropriate tools. Output only the tool invocation. Do not include any explanations or additional text."
        )
        systemMessage = SystemMessage(systemMessageText)

        # setup agent
        self.humanMessageAgent = create_react_agent(
            model, tools, state_modifier=systemMessage
        )

    def _setupCheckClaimsMafiaChain(self) :
        # setup model
        model = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            temperature=0.1,
        )

        # setup prompt
        template = (
            "Respond with \"true\" if the following sentence explicitly claims that {name}'s role is Mafia. Otherwise, respond with \"false\". The likelihood of {name} claiming to be a mafia is extremely low, so you must assess conservatively. Respond with \"true\" if the following sentence explicitly claims that {name}'s role is Mafia, even if there are minor grammatical errors. Otherwise, respond with \"false\"."
            "\n\n"
            "examples"
            "\n"
            "I am a mafia. - \"true\""
            "\n"
            "{name} is a mafia. - \"true\""
            "\n"
            "{name} was acting strange, but we can't be sure of their role. - \"false\""
            "\n"
            "There's no proof that {name} is Mafia. - \"false\""
            "\n"
            "You are a Mafia. - \"false\""
            "\n"
            "The mafia is you. - \"false\""
            "\n\n"
            "sentence: {sentence}"
        )
        prompt = PromptTemplate.from_template(template)

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.checkClaimsMafiaChain = prompt | model | parser

    def _setupCheckQuestionChain(self) :
        # setup model
        model = ChatAnthropic(
            model="claude-3-5-haiku-20241022",
            temperature=0.1,
        )

        # setup prompt
        template = (
            "Respond with \"true\" if ##message## is a question; otherwise, respond with \"false\"."
            "\n\n"
            "##message##"
            "\n"
            "{message}"
        )
        prompt = PromptTemplate.from_template(template)

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.checkQuestionChain = prompt | model | parser

    def _setupGenerateResponseChain(self, gameInfo: GameInfo) :
        # setup model
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.9,
        )

        # setup prompt
        systemMessageTemplate = (
            "Below is a conversation snippet from a Mafia game. Generate the name of the participant who will respond to the message \"{lastMessage}\" and their response message in JSON format. The name must be one from the {nameList}. You can freely and creatively write the content of the response message, but it must be something plausible within the context of a Mafia game and must not contradict the participant's previous claims. Keep your statement concise, limited to two sentences, written in %(language)s and resembling natural dialogue. For the JSON format, provide only the JSON itself as the output, without enclosing it in code blocks or additional text."
            "\n\n"
            "##JSON format##"
            "\n"
            '\"{{"name":"", "message":""}}\"'
        )
        systemMessageTemplate = systemMessageTemplate % {
            'language' : gameInfo.language,
        }
        prompt = ChatPromptTemplate.from_messages(
            [
                ('system', systemMessageTemplate),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.generateResponseChain = prompt | model | parser

    def _setupGenerateQuestionChain(self, gameInfo: GameInfo) :
        # setup model
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.9,
        )

        # setup prompt
        systemMessageTemplate = (
            "You are a player participating in a Mafia game. Your name is {my_name}. You suspect that {name} is the mafia, so you are about to ask them a question. Please write a question to ask them. The content of the question is free and creative, but it should be plausible within the context of the mafia game. Keep your statement concise, limited to two sentences, and written in a {tone} tone, written in %(language)s and resembling natural dialogue. %(dont_tranlate)s"
        )
        systemMessageTemplate = systemMessageTemplate % {
            'language' : gameInfo.language,
            'dont_tranlate' : ' Do not translate into english.' if gameInfo.language != 'english' else '',
        }
        prompt = ChatPromptTemplate.from_messages(
            [
                ('system', systemMessageTemplate),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.generateQuestionChain = prompt | model | parser

    def _setupGenerateNormalDiscussionChain(self, gameInfo: GameInfo) :
        # setup model
        model = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            temperature=0.9,
        )

        # setup prompt
        systemMessageTemplate = (
            "You are a participant in a mafia game. Your name is {my_name}. Instead of suspecting someone, you want to speak freely. Please write what you would say. If you want to mention another participant, refer to ##List of Other Participants##. However, you must not state that someone is the mafia, regardless of intent, nor reveal that your role is anything other than a citizen or imply that you are not a citizen. Keep your statement concise, limited to two sentences, and written in a {tone} tone, written in %(language)s and resembling natural dialogue. %(dont_tranlate)s"
            "\n\n"
            "##List of Other Participants##"
            "\n"
            "{otherParticipants}"
        )
        systemMessageTemplate = systemMessageTemplate % {
            'language' : gameInfo.language,
            'dont_tranlate' : ' Do not translate into english.' if gameInfo.language != 'english' else '',
        }
        prompt = ChatPromptTemplate.from_messages(
            [
                ('system', systemMessageTemplate),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # setup parser
        parser = StrOutputParser()

        # setup chain
        self.generateNormalDiscussionChain = prompt | model | parser

    async def _ainvokeChain(self, chain: RunnableSerializable[dict, BaseMessage], input: dict[str, str]) -> BaseMessage :
        try :
            return await chain.ainvoke(input)
        except ValueError as e:
            self.logger.log(TAG.ERROR, f"[LLM] ValueError: {e}")
            raise e
        except KeyError as e:
            self.logger.log(TAG.ERROR, f"[LLM] KeyError: Missing key - {e}")
            raise e
        # except openai.error.AuthenticationError as e:
        #     self.logger.log(TAG.ERROR, f"[LLM] AuthenticationError: {e}")
        #     raise e
        # except openai.error.RateLimitError as e:
        #     self.logger.log(TAG.ERROR, f"[LLM] RateLimitError: {e}")
        #     raise e
        # except openai.error.APIError as e:
        #     self.logger.log(TAG.ERROR, f"[LLM] APIError: {e}")
        #     raise e
        # except openai.error.Timeout as e:
        #     self.logger.log(TAG.ERROR, f"[LLM] TimeoutError: {e}")
        #     raise e
        # except openai.error.InvalidRequestError as e:
        #     self.logger.log(TAG.ERROR, f"[LLM] InvalidRequestError: {e}")
        #     raise e
        # except LangChainError as e:
        #     self.logger.log(TAG.ERROR, f"[LLM] LangChainError: {e}")
        #     raise e
        except TypeError as e:
            self.logger.log(TAG.ERROR, f"[LLM] TypeError: {e}")
            raise e
        except Exception as e:
            self.logger.log(TAG.ERROR, f"[LLM] Unexpected error: {e}")
            raise e
