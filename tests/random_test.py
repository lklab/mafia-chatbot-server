import numpy as np
import matplotlib.pyplot as plt

def generate_random_value(mode, value_range, spread, sample_size=1):
    """
    주어진 최빈값(mode), 값의 범위(value_range), 퍼짐 정도(spread)에 맞춰 삼각분포에서 랜덤 값 생성.
    
    :param mode: 최빈값 (범위 내 값)
    :param value_range: 값의 범위 (예: (0.0, 2.0) 형태)
    :param spread: 퍼짐 정도 (퍼짐 정도가 클수록 양 끝값의 확률이 커짐)
    :param sample_size: 생성할 샘플 개수 (기본값: 1)
    :return: 생성된 랜덤 값 또는 값의 배열
    """
    min_value, max_value = value_range
    
    # 최빈값을 범위에 맞게 변환
    mode_normalized = (mode - min_value) / (max_value - min_value)  # [0, 1] 범위로 정규화
    
    # 퍼짐 정도에 맞춰 scale 계산
    scale = spread
    
    # 삼각분포에서 값 생성
    samples = np.random.triangular(min_value, mode, max_value, size=sample_size)
    
    return samples

# 사용 예시
mode = 1  # 최빈값 (0.0~2.0 범위 내)
value_range = (0.0, 2.0)  # 값의 범위 (0.0~2.0)
spread = 0.00001  # 퍼짐 정도 (값이 작으면 중앙 집중, 커지면 퍼짐)

# 랜덤 값 생성
random_values = generate_random_value(mode, value_range, spread, sample_size=10000)

# 결과 확인
plt.hist(random_values, bins=50, density=True, alpha=0.7, color='blue', label='Random Values')
plt.axvline(mode, color='red', linestyle='--', label='Mode')
plt.legend()
plt.show()
