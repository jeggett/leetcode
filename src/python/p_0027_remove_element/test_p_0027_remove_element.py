import pytest

from p_0027_remove_element import Solution


solution = Solution()


@pytest.mark.parametrize(
    ("nums", "value", "expected"),
    [
        pytest.param([3, 2, 2, 3], 3, [2, 2], id="removes-duplicates"),
        pytest.param([0, 1, 2, 2, 3, 0, 4, 2], 2, [0, 0, 1, 3, 4], id="mixed"),
        pytest.param([], 1, [], id="empty"),
        pytest.param([1, 1], 1, [], id="all-removed"),
        pytest.param([1, 2], 3, [1, 2], id="none-removed"),
    ],
)
def test_remove_element_mutates_the_valid_prefix(
    nums: list[int], value: int, expected: list[int]
) -> None:
    length = solution.removeElement(nums=nums, val=value)

    assert length == len(expected)
    assert sorted(nums[:length]) == expected
