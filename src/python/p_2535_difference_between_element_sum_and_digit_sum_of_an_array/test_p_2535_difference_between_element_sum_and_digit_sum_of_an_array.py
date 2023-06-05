from p_2535_difference_between_element_sum_and_digit_sum_of_an_array import Solution


solution = Solution()


def test_p_2535_difference_between_element_sum_and_digit_sum_of_an_array():
    assert solution.differenceOfSum(nums=[1, 15, 6, 3]) == 9
    assert solution.differenceOfSum([1, 2, 3, 4]) == 0
