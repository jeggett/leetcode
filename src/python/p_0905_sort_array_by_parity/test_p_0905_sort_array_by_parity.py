from p_0905_sort_array_by_parity import Solution


solution = Solution()


def test_p_905_sort_array_by_parity():
    assert solution.sortArrayByParity([3, 1, 2, 4]) == [2, 4, 3, 1]
    assert solution.sortArrayByParity([0]) == [0]
