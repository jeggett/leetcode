from p_2652_sum_multiples import Solution


solution = Solution()


def test_p_2652_sum_multiples():
    assert solution.sumOfMultiples(7) == 21
    assert solution.sumOfMultiples(10) == 40
    assert solution.sumOfMultiples(9) == 30
