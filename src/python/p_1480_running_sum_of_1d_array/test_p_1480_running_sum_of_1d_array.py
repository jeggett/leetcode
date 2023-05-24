from p_1480_running_sum_of_1d_array import Solution

solution = Solution()


def test_p_1480_running_sum_of_1d_array():
    assert solution.runningSum([1, 2, 3, 4]) == [1, 3, 6, 10]
    assert solution.runningSum([1, 1, 1, 1, 1]) == [1, 2, 3, 4, 5]
