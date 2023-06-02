from typing import List


class OrderedStream:
    """time: O(N), space: O(1)"""

    def __init__(self, n: int):
        self.__arr = [None for _ in range(n)]
        self.__ptr = 0

    def insert(self, idKey: int, value: str) -> List[str]:
        idKey -= 1
        self.__arr[idKey] = value
        if self.__arr[self.__ptr] is None:
            return []
        while self.__ptr < len(self.__arr) and self.__arr[self.__ptr] is not None:
            self.__ptr += 1

        return self.__arr[idKey : self.__ptr]
