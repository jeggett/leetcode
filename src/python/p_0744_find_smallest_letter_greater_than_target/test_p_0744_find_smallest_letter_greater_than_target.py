from p_0744_find_smallest_letter_greater_than_target import Solution


solution = Solution()


def test_p_0744_find_smallest_letter_greater_than_target():
    assert solution.nextGreatestLetter(letters=["c", "f", "j"], target="a") == "c"
    assert solution.nextGreatestLetter(letters=["c", "f", "j"], target="c") == "f"
    assert solution.nextGreatestLetter(letters=["x", "x", "y", "y"], target="z") == "x"
