from p_2574_left_and_right_sum_differences import Solution

solution = Solution()


def test_p_2574_left_and_right_sum_differences():
    assert solution.leftRightDifference([10, 4, 8, 3]) == [15, 1, 11, 22]
    assert solution.leftRightDifference([1]) == [0]
