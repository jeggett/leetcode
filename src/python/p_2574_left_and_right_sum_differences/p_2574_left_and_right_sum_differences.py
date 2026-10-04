class Solution:
    # time: O(n), space: O(1) excluding the result
    def leftRightDifference(self, nums: list[int]) -> list[int]:
        left = 0
        right = sum(nums)
        answer = []
        for num in nums:
            right -= num
            answer.append(abs(left - right))
            left += num
        return answer
