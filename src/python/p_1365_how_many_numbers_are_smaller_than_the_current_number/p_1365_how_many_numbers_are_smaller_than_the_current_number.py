from typing import List


class Solution:
    def smallerNumbersThanCurrent(self, nums: List[int]) -> List[int]:
        result = []
        for num in nums:
            count = 0
            for inner in nums:
                if inner < num:
                    count += 1
            result.append(count)

        return result
