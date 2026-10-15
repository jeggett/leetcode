class Solution:
    """time: O(N), space: O(1)"""

    def countMatches(self, items: list[list[str]], ruleKey: str, ruleValue: str) -> int:
        index = {"type": 0, "color": 1, "name": 2}[ruleKey]
        count = 0
        for item in items:
            if item[index] == ruleValue:
                count += 1

        return count
