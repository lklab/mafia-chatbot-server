import firebase_admin
from firebase_admin import credentials

cred = credentials.Certificate("firebase-adminsdk.json")
firebase_admin.initialize_app(cred)

from firebase_admin import auth

user = auth.get_user('c8x3IyWzKme44T9Ncukn2oeQ4rc2')
print('Successfully fetched user data: {0}'.format(user.email))
