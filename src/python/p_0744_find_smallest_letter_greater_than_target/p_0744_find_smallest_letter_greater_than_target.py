class Solution:
    """time O(N), space O(N)"""

    def nextGreatestLetter(self, letters: list[str], target: str) -> str:
        return min(list(filter(lambda char: ord(char) > ord(target), letters)) or letters[0])
