from p_1389_create_target_array_in_the_given_order import Solution


solution = Solution()


def test_p_1389_create_target_array_in_the_given_order():
    assert solution.createTargetArray([0, 1, 2, 3, 4], [0, 1, 2, 2, 1]) == [0, 4, 1, 3, 2]
    assert solution.createTargetArray([1, 2, 3, 4, 0], [0, 1, 2, 3, 0]) == [0, 1, 2, 3, 4]
    assert solution.createTargetArray([1], [0]) == [1]
