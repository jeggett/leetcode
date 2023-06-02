from p_1528_shuffle_string import Solution


solution = Solution()


def test_p_1528_shuffle_string():
    assert solution.restoreString(s="codeleet", indices=[4, 5, 6, 7, 0, 2, 1, 3]) == "leetcode"
    assert solution.restoreString(s="abc", indices=[0, 1, 2]) == "abc"
