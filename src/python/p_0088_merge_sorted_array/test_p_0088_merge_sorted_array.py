import pytest

from p_0088_merge_sorted_array import Solution


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 2, 3], [2, 5, 6], [1, 2, 2, 3, 5, 6]),
        ([1], [], [1]),
        ([], [1], [1]),
        ([4, 5], [1, 2, 3], [1, 2, 3, 4, 5]),
        ([1, 2], [3, 4], [1, 2, 3, 4]),
        ([], [], []),
    ],
)
def test_merge(left: list[int], right: list[int], expected: list[int]) -> None:
    nums1 = left + [0] * len(right)
    original_right = right.copy()
    assert Solution().merge(nums1, len(left), right, len(right)) is None
    assert nums1 == expected
    assert right == original_right
