from typing import List


class Solution:
    def decode(self, encoded: List[int], first: int) -> List[int]:
        original = [first]
        for i in range(0, len(encoded)):
            original.append(encoded[i] ^ original[i])
        return original
