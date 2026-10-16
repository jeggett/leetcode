/** LeetCode's node shape: O(1) construction. */
export class TreeNode {
    constructor(
        public val: number = 0,
        public left: TreeNode | null = null,
        public right: TreeNode | null = null,
    ) {}
}

/** O(n) time and space; null entries represent missing children. */
export function treeFromLevelOrder(values: readonly (number | null)[]): TreeNode | null {
    if (values.length === 0 || values[0] === null) {
        return null;
    }
    const root = new TreeNode(values[0]);
    const queue = [root];
    let valueIndex = 1;
    for (let index = 0; index < queue.length && valueIndex < values.length; index++) {
        const parent = queue[index];
        const left = values[valueIndex++];
        if (left !== null) {
            parent.left = new TreeNode(left);
            queue.push(parent.left);
        }
        if (valueIndex < values.length) {
            const right = values[valueIndex++];
            if (right !== null) {
                parent.right = new TreeNode(right);
                queue.push(parent.right);
            }
        }
    }
    return root;
}

/** O(n) time and space; omits trailing null entries. */
export function treeToLevelOrder(root: TreeNode | null): (number | null)[] {
    const values: (number | null)[] = [];
    const queue: (TreeNode | null)[] = [root];
    for (let index = 0; index < queue.length; index++) {
        const node = queue[index];
        if (node === null) {
            values.push(null);
        } else {
            values.push(node.val);
            queue.push(node.left, node.right);
        }
    }
    while (values.length > 0 && values[values.length - 1] === null) {
        values.pop();
    }
    return values;
}
