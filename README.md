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
pip install -U langchain langchain-openai langchain-google-genai langchain-anthropic langgraph
```

``` bash
pip install protobuf firebase-admin
```

3. In the root directory of the repository, create a file called `config/apikeys.json` and configure your API keys:
    * If the `config` directory does not exist in the project root, create it.
    * To get an OpenAI API key, visit [https://platform.openai.com/api-keys](https://platform.openai.com/api-keys). Please note that payment is required to use the key.
    * To get an Google API key, visit [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey). Please note that payment is required to use the key.
    * To get an Anthropic API key, visit [https://console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys). Please note that payment is required to use the key.
    * (optional) To obtain a Langchain API key, log in at [https://smith.langchain.com](https://smith.langchain.com) and generate your key.

``` json
{
    "OPENAI_API_KEY": "your_openai_api_key_here",
    "GOOGLE_API_KEY": "your_google_api_key_here",
    "ANTHROPIC_API_KEY": "your_anthropic_api_key_here",
    "LANGCHAIN_API_KEY": "(optional) your_langchain_api_key_here"
}
```

4. Place your Firebase admin file at `config/firebase-adminsdk.json`.

5. Compile l10n files
    * run /mafia_chatbot/locales/tools/msgfmt.py file
    * gettext required

6. Create a `config/operation_info.json` file with the following content:

``` json
{
    "requiredVersion": "0.3.7",
    "operating": true,
    "stateMessage": {
        "german": "Derzeit wird der Server gewartet.",
        "english": "The server is currently under maintenance.",
        "spanish": "El servidor está actualmente en mantenimiento.",
        "french": "Le serveur est actuellement en maintenance.",
        "italian": "Il server è attualmente in manutenzione.",
        "japanese": "現在、サーバーはメンテナンス中です。",
        "korean": "현재 서버 점검 중입니다.",
        "portuguese": "O servidor está atualmente em manutenção.",
        "russian": "В настоящее время сервер находится на обслуживании.",
        "thai": "ขณะนี้เซิร์ฟเวอร์อยู่ระหว่างการบำรุงรักษา",
        "vietnamese": "Máy chủ hiện đang được bảo trì.",
        "simplified chinese": "服务器目前正在维护。",
        "traditional chinese": "伺服器目前正在維護中。",
        "trailingComma": ""
    },
    "maintainEndTime": "2025-02-12T10:30:00Z",
    "enableAds": false
}
```

7. Create a `config/server_config.json` file with the following content:
    * Replace "path-to-your-tls-certfile" and "path-to-your-tls-keyfile" with the actual paths to your TLS certificate and key files.

``` json
{
    "main_port": 10015,
    "first_game_port": 10016,
    "ipc_port": 30000,
    "game_process_count": 8,
    "certfile": "path-to-your-tls-certfile",
    "keyfile": "path-to-your-tls-keyfile"
}
```

### Run

1. Move your working directory to the root of the repository:

``` bash
cd {repository root}
```

2. Run the application:

``` bash
python tests/game/game_test.py
```
