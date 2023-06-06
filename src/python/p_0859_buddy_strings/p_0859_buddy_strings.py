from typing import List
from collections import Counter


class Solution:
    def buddyStrings(self, s: str, goal: str) -> bool:
        if len(s) == 1 or len(s) != len(goal):
            return False

        indices = []
        for i in range(0, len(s)):
            if s[i] != goal[i]:
                indices.append(i)
            if len(indices) > 2:
                return False

        if len(indices) == 1:
            return False

        # check for repeating symbols
        if len(indices) == 0:
            return any(filter(lambda x: x > 1, list(Counter(list(s)).values())))

        # only len(indices) == 2 case is left
        return s[indices[0]] == goal[indices[1]] and s[indices[1]] == goal[indices[0]]
