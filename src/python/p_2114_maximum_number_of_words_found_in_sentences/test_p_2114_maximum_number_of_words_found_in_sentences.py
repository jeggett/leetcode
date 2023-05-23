from p_2114_maximum_number_of_words_found_in_sentences import Solution

solution = Solution()


def test_p_2114_maximum_number_of_words_found_in_sentences():
    assert (
        solution.mostWordsFound(
            ["alice and bob love leetcode", "i think so too", "this is great thanks very much"]
        )
    ) == 6
    assert solution.mostWordsFound(["please wait", "continue to fight", "continue to win"]) == 3
