import pytest

from src.python.data_structures.helpers import (
    list_from_array,
    list_to_array,
    tree_from_level_order,
    tree_to_level_order,
)
from src.python.data_structures.linked_list import ListNode
from src.python.data_structures.tree import TreeNode


def test_node_defaults_and_links() -> None:
    node = ListNode()
    assert node.val == 0 and node.next is None
    assert ListNode(1, node).next is node
    child = TreeNode()
    assert child.val == 0 and child.left is None and child.right is None
    assert TreeNode(1, child, child).right is child


@pytest.mark.parametrize("values", [[], [0], [1, 1, 2], [-1, 0, 3]])
def test_list_round_trip_without_mutating_input(values: list[int]) -> None:
    original = values.copy()
    head = list_from_array(values)
    assert list_to_array(head) == original
    assert values == original
    assert list_to_array(list_from_array(list_to_array(head))) == original


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([], []),
        ([None], []),
        ([0], [0]),
        ([1, 1, 1], [1, 1, 1]),
        ([1, None, 2, 3, None, None, 4], [1, None, 2, 3, None, None, 4]),
        ([1, 2, None, None, 3, None, None], [1, 2, None, None, 3]),
    ],
)
def test_tree_round_trip_without_mutating_input(
    values: list[int | None], expected: list[int | None]
) -> None:
    original = values.copy()
    root = tree_from_level_order(values)
    assert tree_to_level_order(root) == expected
    assert values == original
    assert tree_to_level_order(tree_from_level_order(tree_to_level_order(root))) == expected


def test_sparse_tree_shape() -> None:
    root = tree_from_level_order([1, None, 2, 3])
    assert root is not None and root.left is None
    assert root.right is not None and root.right.left is not None
    assert root.right.left.val == 3
