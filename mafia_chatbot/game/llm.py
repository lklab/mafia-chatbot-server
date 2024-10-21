if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).parents[2]
    sys.path.append(str(path_root))

import json
import os
from typing import Optional, Type
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.callbacks import (
    CallbackManagerForToolRun,
)
from langchain_core.tools import BaseTool, StructuredTool
from langchain_core.messages import SystemMessage
from langchain_core.messages.tool import ToolMessage
from langgraph.prebuilt import create_react_agent

from mafia_chatbot.game.game_state import *
from mafia_chatbot.game.player import *
from mafia_chatbot.game.player_info import *

class LLM :
    def __init__(self, gameState: GameState, language: str) :
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
        discussionPrompt = self._setupDiscussionPrompt(language)
        self.discussionChain = discussionPrompt | model

        # setup human message agent
        self.humanMessageAgent = self._setupHumanMessageAgent(model, self.gameState.nameList)

    def getDiscussion(self, gameState: GameState, player: Player) :
        response = self.discussionChain.invoke({
            'gameState': gameState,
            'player': player,
        })
        return response.content

    def analyzeHumanMessage(self, player: Player, message: str) -> Strategy :
        response = self.humanMessageAgent.invoke({'messages': [('user', message)]})

        for message in reversed(response['messages']) :
            if isinstance(message, ToolMessage) :
                data = json.loads(message.content)

                publicRole: Role = None
                if 'role' in data :
                    publicRole = strToRole(data['role'])
                if publicRole == None :
                    publicRole = player.publicRole

                estimations: list[Estimation] = []
                for estimation in data['estimations'] :
                    playerInfo: PlayerInfo = self.gameState.getPlayerInfoByName(estimation['name'])
                    role: Role = strToRole(estimation['role'])
                    if playerInfo != None and role != None :
                        estimations.append(Estimation(playerInfo, role))

                assumptions: list[Assumption] = [Assumption(estimations, '')]

                strategy: Strategy = Strategy(publicRole, assumptions)
                return strategy

        return None

    def _setupDiscussionPrompt(self, language: str) :
        def _preprocessInput(input) :
            gameState: GameState = input['gameState']
            player: Player = input['player']

            roleToTeam = {
                Role.CITIZEN: 'Citizen',
                Role.MAFIA: 'Mafia',
                Role.POLICE: 'Citizen',
                Role.DOCTOR: 'Citizen',
            }

            return {
                'citizen_count': gameState.gameInfo.citizenCount,
                'mafia_count': gameState.gameInfo.mafiaCount,
                'players_list': ','.join(map(lambda p: p.info.name, gameState.allPlayers)),
                'my_name': player.info.name,
                'my_team': roleToTeam[player.info.role],
                'mafias_list': "Unknown" if player.info.role != Role.MAFIA else ','.join(map(lambda p: p.info.name, gameState.allMafiaPlayers)),
                'language': language,
                'tone': player.info.tone,
                'surviving_citizen_count': gameState.getCitizenCount(),
                'surviving_mafia_count': gameState.getMafiaCount(),
                'survivors_list': ','.join(map(lambda p: p.info.name, gameState.players)),
                'current_step': f'Day {gameState.round + 1}',
                'discussion_history': '\n'.join(gameState.discussionHistory),
                'discussion_role': player.getRolePrompt(),
                'discussion_assumptions': player.discussionStrategy.assumptionsToPrompt(),
            }

        def _setupInformationPrompt(input) :
            return informationTemplate.invoke(input).text

        def _setupHistoryPrompt(input) :
            return historyTemplate.invoke(input).text

        def _setupStrategyPrompt(input) :
            return strategyTemplate.invoke(input).text

        templateText = (
            "## Game Rules"
            "\nYou are participating in a Mafia game. In the Mafia game, there are two teams: the Citizen team and the Mafia team. Each night, one person is chosen by vote to be executed, and their role is revealed. The Citizens win if all Mafia members are executed, while the Mafia team wins if the number of surviving Citizens becomes equal to or fewer than the number of Mafia. You need to create suitable discussion statements considering the game information and history below, to align with your discussion strategy. Write discussion sentences in a conversational tone, concise, without line breaks or colons, and within two sentences in {language}. You should use a {tone} tone and speak differently from others."
            "\n\n## Game Information"
            "\n{information}"
            "\n\n## Game History"
            "\n{history}"
            "\n\n## Discussion Strategy"
            "\n{strategy}"
        )
        informationTemplateText = '\n'.join([
            "Participants: {citizen_count} Citizens, {mafia_count} Mafia",
            "Participant List: {players_list}",
            "Your Name: {my_name}",
            "Your Team: {my_team}",
            "List of Mafia: {mafias_list}",
            "Discussion Language: {language}",
        ])
        historyTemplateText = '\n'.join([
            "Surviving Participants: {surviving_citizen_count} Citizens, {surviving_mafia_count} Mafia",
            "Survivor List: {survivors_list}",
            "Current Step: {current_step}",
            "Discussion History:\n{discussion_history}",
        ])
        strategyTemplateText = '\n'.join([
            "{discussion_role}",
            "{discussion_assumptions}",
        ])

        template = PromptTemplate.from_template(templateText)
        informationTemplate = PromptTemplate.from_template(informationTemplateText)
        historyTemplate = PromptTemplate.from_template(historyTemplateText)
        strategyTemplate = PromptTemplate.from_template(strategyTemplateText)

        prompt = (
            RunnableLambda(_preprocessInput)
            | RunnablePassthrough.assign(information=RunnableLambda(_setupInformationPrompt))
            | RunnablePassthrough.assign(history=RunnableLambda(_setupHistoryPrompt))
            | RunnablePassthrough.assign(strategy=RunnableLambda(_setupStrategyPrompt))
            | template
        )

        return prompt

    def _setupHumanMessageAgent(self, model, nameList: list[str]) :
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
