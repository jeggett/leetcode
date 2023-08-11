from typing import List


class Solution:
    def removeElement(self, nums: List[int], val: int) -> int:
        i, j = 0, len(nums) - 1
        while i <= j:
            if nums[i] == val:
                nums[i] = nums[j]
                del nums[j]
                j -= 1
            else:
                i += 1

        return j + 1


solution = Solution()

solution.removeElement([1], 1)
