class Solution:
    def decode(self, encoded: list[int], first: int) -> list[int]:
        original = [first]
        for i in range(0, len(encoded)):
            original.append(encoded[i] ^ original[i])
        return original
