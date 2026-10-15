class Solution:
    def getConcatenation(self, nums: list[int]) -> list[int]:
        # instead of returning nums*2
        ans = nums[:]
        for i in range(0, len(nums)):
            ans.append(nums[i])

        return ans
