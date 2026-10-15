class Solution:
    def buildArray(self, nums: list[int]) -> list[int]:
        # with extra space
        return list(map(lambda index: nums[index], nums))


# TODO solve without extra space using Euclid's long division lemma.
