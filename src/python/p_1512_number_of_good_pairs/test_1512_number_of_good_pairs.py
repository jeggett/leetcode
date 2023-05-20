from p_1512_number_of_good_pairs import Solution

solution = Solution()


def test_p_1512_number_of_good_pairs():
    assert solution.numIdenticalPairs([1, 2, 3, 1, 1, 3]) == 4
    assert solution.numIdenticalPairs([1, 1, 1, 1]) == 6
    assert solution.numIdenticalPairs([1, 2, 3]) == 0
    assert solution.numIdenticalPairs([0]) == 0
