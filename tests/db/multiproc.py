if __name__ == "__main__" :
    from pathlib import Path
    import sys

    path_root = Path(__file__).resolve().parent
    while path_root.name != 'mafia-chatbot-server' :
        path_root = path_root.parent

    sys.path.append(str(path_root))

import multiprocessing
import random
import string
import time
from sqlite3 import OperationalError

# DB 클래스 Import (UserDB가 정의되어 있다고 가정)
from mafia_chatbot.db.user_db import userDB

# 공유 데이터베이스 인스턴스 생성
db_instance = userDB
db_instance.enable_wal()

# 프로세스 함수: 데이터 읽기 작업 수행
def reader_process():
    for i in range(100000):
        if i % 10000 == 0 :
            print(f'reader i={i}')

        a = (i % 100) + 1
        uid = str(a)
        try:
            data = db_instance.get_user_by_uid(uid)
            if data != None and int(data[1]) % int(data[0]) != 0 :
                print(f'Error! id={data[0]}, name={data[1]}')
        except OperationalError as e:
            print(f"[Reader] Error: {e}")

# 프로세스 함수: 데이터 읽기/쓰기 작업 수행
def writer_process():
    for i in range(100000):
        if i % 1000 == 0 :
            print(f'writer i={i}')

        a = (i % 100) + 1
        b = (i // 100) + 1
        uid = str(a)
        name = str(a * b)
        try:
            db_instance.upsert_user(uid, name)  # 데이터 삽입 또는 업데이트
            data = db_instance.get_user_by_uid(uid)   # 데이터 읽기
            if data == None :
                print(f'Error! id={a} is None')
            elif data[0] != str(a) or data[1] != str(a * b) :
                print(f'Error! id={a}, b={b}, data[0]={data[0]}, data[1]={data[1]}')
        except OperationalError as e:
            print(f"[Writer] Error: {e}")

# 메인 함수
def main():
    processes = []

    # 읽기 전용 프로세스 8개 생성
    for _ in range(8):
        p = multiprocessing.Process(target=reader_process)
        processes.append(p)

    # 읽기/쓰기 혼합 프로세스 1개 생성
    writer = multiprocessing.Process(target=writer_process)
    processes.append(writer)

    # 모든 프로세스 시작
    for p in processes:
        p.start()

    # 모든 프로세스 종료 대기
    for p in processes:
        p.join()

    # 최종 체크
    for i in range(100):
        uid = str(i + 1)
        data = db_instance.get_user_by_uid(uid)
        if data == None :
            print(f'Error! final id={uid} is None')
            continue
        if data[0] != uid or int(data[1]) != 1000 * int(data[0]) :
            print(f'Error! final id={uid} data[0]={data[0]}, data[1]={data[1]}')
            continue

    print("Test completed.")

if __name__ == "__main__":
    main()
