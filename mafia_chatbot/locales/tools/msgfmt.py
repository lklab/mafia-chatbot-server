import os
import subprocess

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

for locale in locales :
    result = subprocess.run([
        'msgfmt',
        os.path.join('mafia_chatbot/locales', locale, 'LC_MESSAGES/messages.po'),
        '-o',
        os.path.join('mafia_chatbot/locales', locale, 'LC_MESSAGES/messages.mo'),
    ], capture_output=True, text=True)

    if result.returncode != 0 :
        print(f'\033[31mfail to msgfmt:\033[0m {result.stderr}')
        exit()
