class Solution:
    def finalValueAfterOperations(self, operations: list[str]) -> int:
        n = 0
        for operation in operations:
            if "+" in operation:
                n += 1
            else:
                n -= 1
        return n
