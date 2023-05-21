from p_1431_kids_with_the_greatest_number_of_candies import Solution

solution = Solution()


def test_p_1431_kids_with_the_greatest_number_of_candies():
    assert solution.kidsWithCandies([2, 3, 5, 1, 3], 3) == [True, True, True, False, True]
    assert solution.kidsWithCandies([4, 2, 1, 1, 2], 1) == [True, False, False, False, False]
    assert solution.kidsWithCandies([12, 1, 12], 10) == [True, False, True]
