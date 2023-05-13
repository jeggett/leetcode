from typing import List


class Solution:
    def getConcatenation(self, nums: List[int]) -> List[int]:
        # instead of returning nums*2
        ans = nums[:]
        for i in range(0, len(nums)):
            ans.append(nums[i])

        return ans
