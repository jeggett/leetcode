from typing import List


class Solution:
    """time: O(N), space: O(1)"""

    def sumOfMultiples(self, n: int) -> int:
        # possible one-liner
        # sum([num if self.isDivisible(num) else 0 for num in range(1, n + 1)])
        sum = 0
        for num in range(1, n + 1):
            if num % 3 == 0 or num % 5 == 0 or num % 7 == 0:
                sum += num
        return sum
