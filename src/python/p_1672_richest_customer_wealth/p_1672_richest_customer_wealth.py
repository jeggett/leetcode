class Solution:
    # time: O(m * n), space: O(1)
    def maximumWealth(self, accounts: list[list[int]]) -> int:
        return max(map(sum, accounts))
