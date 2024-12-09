import subprocess

srcFiles: list[str] = [
    'mafia_chatbot/game/game_manager.py',
    'mafia_chatbot/game/game_state.py',
]
destFile: str = 'mafia_chatbot/locales/messages.pot'

result = subprocess.run([
    'xgettext',
    '-d',
    'messages',
    '-o',
    destFile,
] + srcFiles, capture_output=True, text=True)

if result.returncode != 0 :
    print(f'\033[31mfail to xgettext:\033[0m {result.stderr}')
    exit()
