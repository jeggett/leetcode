"""LeetCode's node shape: O(1) construction."""

from __future__ import annotations


class TreeNode:
    def __init__(
        self, val: int = 0, left: TreeNode | None = None, right: TreeNode | None = None
    ) -> None:
        self.val = val
        self.left = left
        self.right = right
