import os
import subprocess

locales: list[str] = [
    'en',
    'ko',
]

for locale in locales :
    result = subprocess.run([
        'msgfmt',
        os.path.join('mafia_chatbot/locales', locale, 'LC_MESSAGES/messages.po'),
        '-o',
        os.path.join('mafia_chatbot/locales', locale, 'LC_MESSAGES/messages.mo'),
    ], capture_output=True, text=True)

    if result.returncode != 0 :
        print(f'\033[31mfail to compile protoc:\033[0m {result.stderr}')
        exit()
