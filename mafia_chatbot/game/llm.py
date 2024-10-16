if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).parents[2]
    sys.path.append(str(path_root))

import json
import os

from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from mafia_chatbot.game.game_state import *
from mafia_chatbot.game.player import *
from mafia_chatbot.game.player_info import *

class LLM :
    def __init__(self, language: str) :
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
        prompt = self._setupPrompt(language)

        # setup chain
        self.chain = prompt | model

    def getDiscussion(self, gameState: GameState, player: Player) :
        response = self.chain.invoke({
            'gameState': gameState,
            'player': player,
        })
        return response.content

    def _setupPrompt(self, language: str) :
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
            "\nYou are participating in a Mafia game. In the Mafia game, there are two teams: the Citizen team and the Mafia team. Each night, one person is chosen by vote to be executed, and their role is revealed. The Citizens win if all Mafia members are executed, while the Mafia team wins if the number of surviving Citizens becomes equal to or fewer than the number of Mafia. You need to create suitable discussion statements considering the game information and history below, to align with your discussion strategy. Write discussion sentences in a conversational tone, concise, without line breaks or colons, and within two sentences in {language}. You should use a tone that is distinct from others whenever possible."
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
