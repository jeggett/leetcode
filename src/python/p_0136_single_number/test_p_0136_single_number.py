from p_0136_single_number import Solution


solution = Solution()


def test_p_136_single_number():
    assert solution.singleNumber([2, 2, 1]) == 1
    assert solution.singleNumber([4, 1, 2, 1, 2]) == 4
    assert solution.singleNumber([1]) == 1
