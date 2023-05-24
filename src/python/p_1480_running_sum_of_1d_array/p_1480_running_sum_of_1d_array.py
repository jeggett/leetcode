from typing import List


class Solution:
    def runningSum(self, nums: List[int]) -> List[int]:
        accumulator = 0
        result = []
        for num in nums:
            accumulator += num
            result.append(accumulator)
        return result
