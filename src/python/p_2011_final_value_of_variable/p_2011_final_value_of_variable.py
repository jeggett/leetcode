from typing import List


class Solution:
    def finalValueAfterOperations(self, operations: List[str]) -> int:
        n = 0
        for operation in operations:
            if "+" in operation:
                n += 1
            else:
                n -= 1
        return n
