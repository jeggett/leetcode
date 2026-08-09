/** LeetCode-provided linked-list node type for solution source files. */
declare class ListNode {
    val: number;
    next: ListNode | null;

    constructor(val?: number, next?: ListNode | null);
}

/** LeetCode-provided binary-tree node type for solution source files. */
declare class TreeNode {
    val: number;
    left: TreeNode | null;
    right: TreeNode | null;

    constructor(val?: number, left?: TreeNode | null, right?: TreeNode | null);
}
