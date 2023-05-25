from typing import List


class Solution:
    """Time: O(n*log(n)). Space: O(1)"""

    def arrayPairSum(self, nums: List[int]) -> int:
        return sum(sorted(nums)[::2])
