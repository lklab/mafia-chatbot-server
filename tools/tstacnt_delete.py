if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import sys
from mafia_chatbot.db.test_account_db import testAccountDB

id = sys.argv[1]
testAccountDB.delete_user_by_id(id)
