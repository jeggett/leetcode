from typing import List


class Solution:
    def maximumWealth(self, accounts: List[List[int]]) -> int:
        # instead of max(map(lambda acc: sum(acc), accounts))
        for i in range(0, len(accounts)):
            sum = accounts[i][0]
            for j in range(1, len(accounts[i])):
                sum += accounts[i][j]
            accounts[i] = sum

        max_wealh = accounts[0]
        for i in range(1, len(accounts)):
            if max_wealh < accounts[i]:
                max_wealh = accounts[i]

        return max_wealh
