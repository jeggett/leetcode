from p_88_merge_sorted_array import Solution


solution = Solution()


def test_p_88_merge_sorted_array():
    nums1 = [1, 2, 3, 0, 0, 0]
    solution.merge(nums1, 3, [2, 5, 6], 3)
    assert nums1 == [1, 2, 2, 3, 5, 6]

    nums1 = [1]
    solution.merge(nums1, 1, [], 0)
    assert nums1 == [1]
