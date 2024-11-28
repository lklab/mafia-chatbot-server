import random

weights = [3, 1]
values = [0, 1]
choices = random.choices(values, weights=weights, k=10000)
print(sum(choices) / 10000)
