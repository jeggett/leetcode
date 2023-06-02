from p_1656_design_an_ordered_stream import OrderedStream


solution = OrderedStream(5)


def test_p_1656_design_an_ordered_stream():
    assert solution.insert(3, "ccccc") == []
    assert solution.insert(1, "aaaaa") == ["aaaaa"]
    assert solution.insert(2, "bbbbb") == ["bbbbb", "ccccc"]
    assert solution.insert(5, "eeeee") == []
    assert solution.insert(4, "ddddd") == ["ddddd", "eeeee"]
