from p_1920_build_array_from_permutation import Solution

solution = Solution()


def test_p_1920_build_array_from_permutation():
    assert solution.buildArray([0, 2, 1, 5, 3, 4]) == [0, 1, 2, 4, 5, 3]
    assert solution.buildArray([5, 0, 1, 2, 3, 4]) == [4, 5, 0, 1, 2, 3]
    assert solution.buildArray([0]) == [0]
