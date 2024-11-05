import socket
import ssl

# 서버 설정
HOST = 'localhost'
PORT = 8443

# 기본 소켓 생성
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# TLS 설정 추가
# context = ssl.create_default_context()
context = ssl._create_unverified_context()
with context.wrap_socket(client_socket, server_hostname=HOST) as tls_client_socket:
    tls_client_socket.connect((HOST, PORT))
    tls_client_socket.send("안녕하세요, 서버!".encode('utf-8'))
    
    data = tls_client_socket.recv(1024).decode('utf-8')
    print("서버로부터 받은 데이터:", data)
