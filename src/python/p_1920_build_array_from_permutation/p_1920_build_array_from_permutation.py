from typing import List


class Solution:
    def buildArray(self, nums: List[int]) -> List[int]:
        # with extra space
        return list(map(lambda index: nums[index], nums))


# TODO solve without extra space using Euclid's long division lemma.
