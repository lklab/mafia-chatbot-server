import os
import json
import subprocess
from string import Template

srcDir = 'mafia_chatbot/network/proto'
dstDir = 'mafia_chatbot/network/messages'

# read index.json
with open(os.path.join(srcDir, 'index.json')) as f :
    index = json.load(f)

# compile proto
for file in index['files'] :
    name = file['name']
    result = subprocess.run([
        'protoc',
        f'--proto_path={srcDir}',
        f'--python_out={dstDir}',
        f'{srcDir}/{name}.proto',
    ], capture_output=True, text=True)

    # print(result)

# generate custom message_info.py
initFileContents = []
typeDict = []
factories = []
factoryDict = []

fileIndex = 0
for file in index['files'] :
    name = file['name']

    initFileContents.append((
f'    \'{name}_pb2\','
    ))

    messageIndex = 0
    for message in file['messages'] :
        msgType = fileIndex + messageIndex

        typeDict.append((
f'    {name}_pb2.{message} : {msgType},'
        ))

        factories.append((
f'def _{message}MessageFactory(data: bytes) -> {name}_pb2.{message} :\n'
f'    message = {name}_pb2.{message}()\n'
f'    message.ParseFromString(data)\n'
f'    return message\n'
        ))

        factoryDict.append((
f'    {msgType} : _{message}MessageFactory,'
        ))

        messageIndex += 1

    fileIndex += 1000

values = {}
values['typeDict'] = '\n'.join(typeDict)
values['factories'] = '\n'.join(factories)
values['factoryDict'] = '\n'.join(factoryDict)

with open(os.path.join(srcDir, 'message_info.py.template')) as f :
    template = Template(f.read())

output = template.substitute(values)
with open(os.path.join(dstDir, 'message_info.py'), 'w') as f :
    f.write(output)

# generate custom __init__.py
values = {}
values['initFileContents'] = '\n'.join(initFileContents)

initFileTemplateStr = (
'__all__ = [\n'
'$initFileContents\n'
']\n'
)
initFileTemplate = Template(initFileTemplateStr)

output = initFileTemplate.substitute(values)
with open(os.path.join(dstDir, '__init__.py'), 'w') as f :
    f.write(output)
