import socket
import ssl

# 서버 설정
HOST = 'localhost'
PORT = 8443

# 기본 소켓 생성
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(5)

# TLS 설정 추가
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(certfile="server.crt", keyfile="server.key")  # 인증서와 키 파일 필요

print("서버가 실행 중입니다...")

# 클라이언트 연결 처리
with context.wrap_socket(server_socket, server_side=True) as tls_server_socket:
    conn, addr = tls_server_socket.accept()
    print(f"클라이언트 {addr}에 연결됨")
    
    data = conn.recv(1024).decode('utf-8')
    print("클라이언트로부터 받은 데이터:", data)
    
    conn.send("안녕하세요, 안전한 연결입니다!".encode('utf-8'))
    conn.close()
