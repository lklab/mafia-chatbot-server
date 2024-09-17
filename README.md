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
```

3. Create an `apikeys.json` file in the root of the repository and configure your API keys:

``` json
{
    "OPENAI_API_KEY": "your_openai_api_key_here",
    "LANGCHAIN_API_KEY": "your_langchain_api_key_here"
}
```

### Run

1. Navigate to the working directory:

``` bash
cd {repository root}/mafia_chatbot
```

2. Run the application:

``` bash
python main.py
```
