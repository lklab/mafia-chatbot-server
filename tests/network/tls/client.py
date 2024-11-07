if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import socket
import ssl

from mafia_chatbot.network.data import *

# 서버 설정
HOST = 'localhost'
PORT = 10015

delimiter = b'\xCA\xFE\xBA\xBE'

# 기본 소켓 생성
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# TLS 설정 추가
# context = ssl.create_default_context()
context = ssl._create_unverified_context()
with context.wrap_socket(client_socket, server_hostname=HOST) as tls_client_socket:
    tls_client_socket.connect((HOST, PORT))

    auth = auth_pb2.Auth()
    auth.rqid = 555
    type = 0
    data = auth.SerializeToString()

    tls_client_socket.send(delimiter +
        type.to_bytes(4, byteorder='big') +
        len(data).to_bytes(4, byteorder='big') +
        data
    )

    buffer = tls_client_socket.recv(4096)

    # check delimiter
    cursor = buffer.find(delimiter)
    cursor += 4

    # get message type and payload size
    msg_type = int.from_bytes(buffer[cursor:cursor+4], byteorder='big')
    cursor += 4
    payload_size = int.from_bytes(buffer[cursor:cursor+4], byteorder='big')
    cursor += 4

    # get payload
    payload = buffer[cursor:cursor+payload_size]
    cursor += payload_size

    # create message
    authResponse = auth_pb2.AuthResponse()
    authResponse.ParseFromString(payload)

    print(f"서버로부터 받은 데이터: type={msg_type}, message=<{authResponse}>")
