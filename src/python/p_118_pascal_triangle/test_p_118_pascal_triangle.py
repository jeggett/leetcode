from p_118_pascal_triangle import Solution


solution = Solution()


def test_p_118_pascal_triangle():
    assert solution.generate(5) == [
        [1],
        [1, 1],
        [1, 2, 1],
        [1, 3, 3, 1],
        [1, 4, 6, 4, 1],
    ]
    assert solution.generate(1) == [[1]]
