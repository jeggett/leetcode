class Solution:
    def shuffle(self, nums: list[int], n: int) -> list[int]:
        if n < 2:
            return nums

        result = []
        for i in range(0, n):
            result.append(nums[i])
            result.append(nums[i + n])
        return result
