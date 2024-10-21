# Mafia chatbot

This is a project to develop a chatbot that can play Mafia game with AI. The project is currently under development. Stay tuned for updates! :)

## Getting started

### Requirements
* Python 3.9 or higher

### Setup
1. Create a virtual environment (recommended):

``` bash
python -m venv .venv
source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
```

2. Install the required Python packages:

``` bash
pip install langchain
pip install -qU langchain-openai
pip install langgraph
```

3. In the root directory of the repository, create a file called `apikeys.json` and configure your API keys:
    * To get an OpenAI API key, visit [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys). Please note that payment is required to use the key.
    * (optional) To obtain a Langchain API key, log in at [https://smith.langchain.com](https://smith.langchain.com) and generate your key.

``` json
{
    "OPENAI_API_KEY": "your_openai_api_key_here",
    "LANGCHAIN_API_KEY": "(optional) your_langchain_api_key_here"
}
```

### Run

1. Move your working directory to the root of the repository:

``` bash
cd {repository root}
```

2. Run the application:

``` bash
python main.py
```
