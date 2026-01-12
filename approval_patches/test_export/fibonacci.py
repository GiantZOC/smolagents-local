"""
Simple fibonacci implementation for testing patch workflow
"""
from typing import Dict


def fibonacci(n):
    """Calculate the nth fibonacci number"""
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        return fibonacci(n - 1) + fibonacci(n - 2)


if __name__ == "__main__":
    for i in range(10):
        print(f"fibonacci({i}) = {fibonacci(i)}")
