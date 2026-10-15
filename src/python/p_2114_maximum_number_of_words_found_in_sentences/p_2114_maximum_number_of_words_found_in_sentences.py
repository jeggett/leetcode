class Solution:
    def mostWordsFound(self, sentences: list[str]) -> int:
        return max(sentence.count(" ") for sentence in sentences) + 1
