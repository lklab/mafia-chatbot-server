if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import sys
import uuid
import random
import string

from mafia_chatbot.db.test_account_db import testAccountDB

def generate_random_id(length=4):
    characters = string.digits
    return 'test-' + ''.join(random.choices(characters, k=length))

def generate_random_pw(length=5):
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choices(characters, k=length))

id = generate_random_id()
pw = generate_random_pw()
clientId = str(uuid.uuid4())
testAccountDB.upsert_user(id, pw, clientId)

print(f'user created: id={id}, pw={pw}, clientId={clientId}')
