from p_561_array_partition import Solution


solution = Solution()


def test_p_561_array_partition():
    assert solution.arrayPairSum([1, 4, 3, 2]) == 4
    assert solution.arrayPairSum([6, 2, 6, 5, 1, 2]) == 9
    assert solution.arrayPairSum([0, 0]) == 0
