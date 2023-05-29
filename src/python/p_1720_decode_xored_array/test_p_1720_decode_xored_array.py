from p_1720_decode_xored_array import Solution


solution = Solution()


def test_p_1720_decode_xored_array():
    assert solution.decode(encoded=[1, 2, 3], first=1) == [1, 0, 2, 1]
    assert solution.decode(encoded=[6, 2, 7, 3], first=4) == [4, 2, 0, 7, 4]
