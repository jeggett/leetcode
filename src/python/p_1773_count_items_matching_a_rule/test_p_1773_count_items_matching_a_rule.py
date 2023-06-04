from p_1773_count_items_matching_a_rule import Solution


solution = Solution()


def test_p_1773_count_items_matching_a_rule():
    assert (
        solution.countMatches(
            items=[
                ["phone", "blue", "pixel"],
                ["computer", "silver", "lenovo"],
                ["phone", "gold", "iphone"],
            ],
            ruleKey="color",
            ruleValue="silver",
        )
        == 1
    )
    assert (
        solution.countMatches(
            items=[
                ["phone", "blue", "pixel"],
                ["computer", "silver", "phone"],
                ["phone", "gold", "iphone"],
            ],
            ruleKey="type",
            ruleValue="phone",
        )
        == 2
    )
