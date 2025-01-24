import os
import json

# load API key
with open('apikeys.json') as f:
    keys = json.load(f)

os.environ["OPENAI_API_KEY"] = keys['OPENAI_API_KEY']
os.environ["GOOGLE_API_KEY"] = keys['GOOGLE_API_KEY']
os.environ["ANTHROPIC_API_KEY"] = keys['ANTHROPIC_API_KEY']

if 'LANGCHAIN_API_KEY' in keys :
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = keys['LANGCHAIN_API_KEY']

from langchain_anthropic import ChatAnthropic

llm = ChatAnthropic(
    # model="claude-3-5-sonnet-20240620",
    model="claude-3-5-haiku-20241022",
    temperature=0,
    max_tokens=1024,
    timeout=None,
    max_retries=2,
    # other params...
)

messages = [
    (
        "system",
        "You are a helpful assistant that translates English to Korean. Translate the user sentence.",
    ),
    ("human", "I love programming."),
]
ai_msg = llm.invoke(messages)
print(ai_msg)
