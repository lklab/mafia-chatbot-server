import os
import datetime

def delete_game_log(path: str, pattern: str, isStarts: bool) :
    # 파일 경로
    directory_path = path
    # 삭제 기준 날짜 차이 (일수)
    threshold_days = 28

    # 현재 날짜
    current_date = datetime.datetime.now()
    pattern_len = len(datetime.datetime.now().strftime(pattern))

    # 파일 목록 읽기
    for filename in os.listdir(directory_path):
        try:
            # 파일명에서 날짜 부분 추출
            date_str = filename[:pattern_len] if isStarts else filename[-pattern_len:]
            file_date = datetime.datetime.strptime(date_str, pattern)

            # 날짜 차이 계산
            date_diff = (current_date - file_date).days
            print(f'{filename}: {date_diff}')

            # 일수 차이가 일정 값 이상이면 파일 삭제
            if date_diff >= threshold_days:
                file_path = os.path.join(directory_path, filename)
                os.remove(file_path)
                print(f'{filename} deleted')
        except ValueError :
            print(f'{filename} delete failed')

delete_game_log('log/', '[%Y%m%d%H%M%S]', True)
delete_game_log('network_log/', '%Y-%m-%d_%H', False)
