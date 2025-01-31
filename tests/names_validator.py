import json
import os

with open(os.path.join('data', 'names.json'), encoding='utf-8') as f :
    data = json.load(f)

# check english name
englishNames: set[str] = set()
for name in data['english']['names'] :
    englishNames.add(name['name'])
print(f'영어 이름 개수: {len(englishNames)}')

for language, langData in data.items() :
    if language == 'english' :
        continue

    nameSet: set[str] = set()
    enNameSet: set[str] = set()
    enNameContained: int = 0

    for name in langData['names'] :
        if name['name'] in nameSet :
            print(f'이름 중복: {name['name']}')
        if name['en'] in enNameSet :
            print(f'영어 이름 중복: {name['en']}')

        nameSet.add(name['name'])
        enNameSet.add(name['en'])

        if name['en'] in englishNames :
            enNameContained += 1

    print(f'{language.ljust(20)}: 이름 개수: {len(nameSet)}, 영어 이름 개수: {len(enNameSet)}, 영어 이름 중복 개수: {enNameContained}')
