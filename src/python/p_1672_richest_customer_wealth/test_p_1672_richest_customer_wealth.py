from p_1672_richest_customer_wealth import Solution


solution = Solution()


def test_p_1672_richest_customer_wealth():
    assert solution.maximumWealth([[1, 2, 3], [3, 2, 1]]) == 6
    assert solution.maximumWealth([[1, 5], [7, 3], [3, 5]]) == 10
    assert solution.maximumWealth([[2, 8, 7], [7, 1, 3], [1, 9, 5]]) == 17
    assert solution.maximumWealth([[0]]) == 0
