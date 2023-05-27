from p_1365_how_many_numbers_are_smaller_than_the_current_number import Solution


solution = Solution()


def test_p_1365_how_many_numbers_are_smaller_than_the_current_number():
    assert solution.smallerNumbersThanCurrent([8, 1, 2, 2, 3]) == [4, 0, 1, 1, 3]
    assert solution.smallerNumbersThanCurrent([6, 5, 4, 8]) == [2, 1, 0, 3]
