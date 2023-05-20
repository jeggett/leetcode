from p_1929_concatenation_of_array import Solution

solution = Solution()


def test_p_1929_concatenation_of_array():
    assert solution.getConcatenation([1, 2, 1]) == [1, 2, 1, 1, 2, 1]
    assert solution.getConcatenation([1, 3, 2, 1]) == [1, 3, 2, 1, 1, 3, 2, 1]
