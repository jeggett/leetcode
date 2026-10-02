"""Plain conversions for tests; submitted solutions use judge-provided types."""

from collections.abc import Sequence

from .linked_list import ListNode
from .tree import TreeNode


def list_from_array(values: Sequence[int]) -> ListNode | None:
    """O(n) time and O(n) nodes; leaves values unchanged."""
    dummy = ListNode()
    tail = dummy
    for value in values:
        tail.next = ListNode(value)
        tail = tail.next
    return dummy.next


def list_to_array(head: ListNode | None) -> list[int]:
    """O(n) time and output space; assumes an acyclic list."""
    values = []
    current = head
    while current is not None:
        values.append(current.val)
        current = current.next
    return values


def tree_from_level_order(values: Sequence[int | None]) -> TreeNode | None:
    """O(n) time and space; None entries represent missing children."""
    if not values or values[0] is None:
        return None
    root = TreeNode(values[0])
    queue = [root]
    value_index = 1
    index = 0
    while index < len(queue) and value_index < len(values):
        parent = queue[index]
        index += 1
        left = values[value_index]
        value_index += 1
        if left is not None:
            parent.left = TreeNode(left)
            queue.append(parent.left)
        if value_index < len(values):
            right = values[value_index]
            value_index += 1
            if right is not None:
                parent.right = TreeNode(right)
                queue.append(parent.right)
    return root


def tree_to_level_order(root: TreeNode | None) -> list[int | None]:
    """O(n) time and space; omits trailing None entries."""
    values = []
    queue = [root]
    index = 0
    while index < len(queue):
        node = queue[index]
        index += 1
        if node is None:
            values.append(None)
        else:
            values.append(node.val)
            queue.extend((node.left, node.right))
    while values and values[-1] is None:
        values.pop()
    return values
