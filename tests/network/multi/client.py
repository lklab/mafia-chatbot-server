import socket
import ssl
import time

delimiter = b'\xCA\xFE\xBA\xBE'

def parseData(data: bytes) :
    # check delimiter
    cursor = data.find(delimiter)
    cursor += 4

    # get message type and payload size
    msg_type = int.from_bytes(data[cursor:cursor+4], byteorder='big')
    cursor += 4
    payload_size = int.from_bytes(data[cursor:cursor+4], byteorder='big')
    cursor += 4

    # get payload
    payload = data[cursor:cursor+payload_size]
    cursor += payload_size

    # return
    return msg_type, payload

# 서버 설정
HOST = 'localhost'
PORT = 10015


# 기본 소켓 생성
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# TLS 설정 추가
# context = ssl.create_default_context()
context = ssl._create_unverified_context()
with context.wrap_socket(client_socket, server_hostname=HOST) as tls_client_socket:
    tls_client_socket.connect((HOST, PORT))
    print(f'Connected main process')

    buffer = tls_client_socket.recv(4096)
    msgType, data = parseData(buffer)
    port = int.from_bytes(data, byteorder='big')
    print(f'Received port: {port}')

    time.sleep(10)
    tls_client_socket.close()
    print(f'Closed')

client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
context = ssl._create_unverified_context()
with context.wrap_socket(client_socket, server_hostname=HOST) as tls_client_socket:
    tls_client_socket.connect((HOST, port))
    print(f'Connected game process')

    for i in range(10) :
        value = i * i
        data = value.to_bytes(4, byteorder='big')
        print(f'Send value: {value}')
        tls_client_socket.send(delimiter +
            msgType.to_bytes(4, byteorder='big') +
            len(data).to_bytes(4, byteorder='big') +
            data
        )

        buffer = tls_client_socket.recv(4096)
        msgType, data = parseData(buffer)
        received = int.from_bytes(data, byteorder='big')
        print(f'Received value: {received}')

        time.sleep(1)

    tls_client_socket.close()
