if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

from mafia_chatbot.db.test_account_db import testAccountDB

testAccountDB.enable_wal()
testAccountDB.upsert_user("user1", "password123", "client1")
print(testAccountDB.get_user_by_id("user1"))
testAccountDB.delete_user_by_id("user1")
