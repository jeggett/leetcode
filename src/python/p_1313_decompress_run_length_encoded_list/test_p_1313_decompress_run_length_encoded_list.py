from p_1313_decompress_run_length_encoded_list import Solution


solution = Solution()


def test_p_1313_decompress_run_length_encoded_list():
    assert solution.decompressRLElist([1, 2, 3, 4]) == [2, 4, 4, 4]
    assert solution.decompressRLElist([1, 1, 2, 3]) == [1, 3, 3]
