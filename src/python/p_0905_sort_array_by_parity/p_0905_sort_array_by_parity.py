class Solution:
    def sortArrayByParity(self, nums: list[int]) -> list[int]:
        even = []
        odd = []
        for num in nums:
            if num % 2 == 0:
                even.append(num)
            else:
                odd.append(num)

        return even + odd
