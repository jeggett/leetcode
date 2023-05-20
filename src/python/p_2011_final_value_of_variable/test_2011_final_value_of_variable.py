from p_2011_final_value_of_variable import Solution

solution = Solution()


def test_p_2011_final_value_of_variable():
    assert solution.finalValueAfterOperations(["--X", "X++", "X++"]) == 1
    assert solution.finalValueAfterOperations(["++X", "++X", "X++"]) == 3
    assert solution.finalValueAfterOperations(["X++", "++X", "--X", "X--"]) == 0
