from typing import List


class Solution:
    """time: O(N), space: O(1)"""

    def differenceOfSum(self, nums: List[int]) -> int:
        result = 0
        for num in nums:
            result += sum([int(digit) for digit in str(num)])
        return abs(sum(nums) - result)
