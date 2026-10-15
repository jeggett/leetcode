class Solution:
    """Time: O(n*log(n)). Space: O(1)"""

    def arrayPairSum(self, nums: list[int]) -> int:
        return sum(sorted(nums)[::2])
