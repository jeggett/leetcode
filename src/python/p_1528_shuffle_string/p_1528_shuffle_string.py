from typing import List


class Solution:
    """time O(N), space O(N)"""

    def restoreString(self, s: str, indices: List[int]) -> str:
        new_arr = [None] * len(s)
        for i in range(len(s)):
            new_arr[indices[i]] = s[i]
        return "".join(new_arr)
