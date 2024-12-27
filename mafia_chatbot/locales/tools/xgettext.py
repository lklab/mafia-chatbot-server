import os
import subprocess

srcFiles: list[str] = [
    'mafia_chatbot/game/game_manager.py',
    'mafia_chatbot/game/game_state.py',
]
potFile: str = 'mafia_chatbot/locales/messages.pot'
locales: list[str] = [
    'en',
    'ko',
]

result = subprocess.run([
    'xgettext',
    '-d',
    'messages',
    '-o',
    potFile,
] + srcFiles, capture_output=True, text=True)

if result.returncode != 0 :
    print(f'\033[31mfail to xgettext:\033[0m {result.stderr}')
    exit()

for locale in locales :
    result = subprocess.run([
        'msgmerge',
        '-U',
        os.path.join('mafia_chatbot/locales', locale, 'LC_MESSAGES/messages.po'),
        potFile,
    ])

    if result.returncode != 0 :
        print(f'\033[31mfail to xgettext:\033[0m {result.stderr}')
        exit()
