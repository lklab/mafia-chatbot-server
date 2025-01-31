import os
import subprocess

srcFiles: list[str] = [
    'mafia_chatbot/game/game_manager.py',
    'mafia_chatbot/game/game_state.py',
]
potFile: str = 'mafia_chatbot/locales/messages.pot'
locales: list[str] = [
    'de-DE',
    'en-US',
    'es-ES',
    'fr-FR',
    'it-IT',
    'ja-JP',
    'ko-KR',
    'pt-BR',
    'ru-RU',
    'th-TH',
    'vi-VN',
    'zh-CN',
    'zh-TW',
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
    poFile = os.path.join('mafia_chatbot/locales', locale, 'LC_MESSAGES/messages.po')
    if os.path.exists(poFile) :
        result = subprocess.run([
            'msgmerge',
            '-U',
            poFile,
            potFile,
        ])
    else :
        os.makedirs(os.path.dirname(poFile), exist_ok=True)
        result = subprocess.run([
            'msginit',
            '--locale', locale,
            '--input', potFile,
            '--output-file', poFile
        ])

    if result.returncode != 0 :
        print(f'\033[31mfail to xgettext:\033[0m {result.stderr}')
        exit()
