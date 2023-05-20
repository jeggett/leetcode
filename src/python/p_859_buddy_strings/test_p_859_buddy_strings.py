from p_859_buddy_strings import Solution

solution = Solution()


def test_p_859_buddy_strings():
    assert solution.buddyStrings("ab", "ba") is True
    assert solution.buddyStrings("ab", "ab") is False
    assert solution.buddyStrings("abab", "abab") is True
    assert solution.buddyStrings("aa", "aa") is True
    assert solution.buddyStrings("abbc", "cbba") is True
    assert solution.buddyStrings("ab", "ca") is False
    assert solution.buddyStrings("ab", "bc") is False
    assert solution.buddyStrings("a", "a") is False
    assert solution.buddyStrings("ac", "cabbb") is False
    assert solution.buddyStrings("acbbb", "ca") is False
