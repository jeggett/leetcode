from p_0027_remove_element import Solution


solution = Solution()


def test_p_0027_remove_element():
    assert solution.removeElement(nums=[3, 2, 2, 3], val=3) == 2
    assert solution.removeElement(nums=[0, 1, 2, 2, 3, 0, 4, 2], val=2) == 5
