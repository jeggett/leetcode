from typing import List


class Solution:
    def leftRightDifference(self, nums: List[int]) -> List[int]:
        answer = []
        for i in range(0, len(nums)):
            answer.append(
                abs(self.computeLeft(nums, i) - self.computeRight(nums, i))
            )

        return answer

    def computeLeft(self, nums: List[int], i: int) -> int:
        left = 0
        for i in range(0, i):
            left += nums[i]
        return left

    def computeRight(self, nums: List[int], i: int) -> int:
        right = 0
        for i in range(i + 1, len(nums)):
            right += nums[i]
        return right
