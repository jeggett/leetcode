from functools import reduce


class Solution:
    """time: O(N), space: O(1)"""

    def singleNumber(self, nums: list[int]) -> int:
        return reduce(lambda num1, num2: num1 ^ num2, nums)
