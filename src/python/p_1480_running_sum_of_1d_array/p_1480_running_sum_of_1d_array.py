class Solution:
    def runningSum(self, nums: list[int]) -> list[int]:
        accumulator = 0
        result = []
        for num in nums:
            accumulator += num
            result.append(accumulator)
        return result
