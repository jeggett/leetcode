from typing import List


class Solution:
    def merge(self, nums1: List[int], m: int, nums2: List[int], n: int) -> None:
        """
        Do not return anything, modify nums1 in-place instead.
        """
        result = []
        i, j = 0, 0
        while i < m and j < n:
            if nums1[i] <= nums2[j]:
                result.append(nums1[i])
                i += 1
            else:
                result.append(nums2[j])
                j += 1

        if i == m:
            result += nums2[j:]
        if j == n:
            result += nums1[i:m]

        for i in range(0, m + n):
            nums1[i] = result[i]
