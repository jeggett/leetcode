class Solution:
    def decompressRLElist(self, nums: list[int]) -> list[int]:
        result = []
        for i in range(0, len(nums), 2):
            result += nums[i] * [nums[i + 1]]
        return result
