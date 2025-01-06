import firebase_admin
from firebase_admin import credentials
from firebase_admin import auth

firebaseInitialized: bool = False

def initialize() :
    global firebaseInitialized
    if firebaseInitialized :
        return

    cred = credentials.Certificate("firebase-adminsdk.json")
    firebase_admin.initialize_app(cred)
    firebaseInitialized = True

def verifyIdToken(token: str) -> str :
    decoded = auth.verify_id_token(token)
    return decoded['uid']

def deleteUser(uid: str) :
    auth.delete_user(uid)

if __name__ == '__main__' :
    initialize()
    print(verifyIdToken('asd'))
