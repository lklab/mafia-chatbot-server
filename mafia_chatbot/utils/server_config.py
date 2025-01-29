import json

serverConfig = None

def _load() :
    global serverConfig
    with open('config/server_config.json', encoding='utf-8') as f :
        serverConfig = json.load(f)

def getMainPort() -> int :
    global serverConfig
    if serverConfig == None :
        _load()
    return serverConfig['main_port']

def getFirstGamePort() -> int :
    global serverConfig
    if serverConfig == None :
        _load()
    return serverConfig['first_game_port']

def getIpcPort() -> int :
    global serverConfig
    if serverConfig == None :
        _load()
    return serverConfig['ipc_port']

def getGameProcessCount() -> int :
    global serverConfig
    if serverConfig == None :
        _load()
    return serverConfig['game_process_count']

def getCertfile() -> str :
    global serverConfig
    if serverConfig == None :
        _load()
    return serverConfig['certfile']

def getKeyfile() -> str :
    global serverConfig
    if serverConfig == None :
        _load()
    return serverConfig['keyfile']
