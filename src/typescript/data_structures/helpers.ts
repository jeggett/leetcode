import { ListNode } from "./linked_list.js";
import { TreeNode } from "./tree.js";

/** O(n) time and O(n) nodes; leaves values unchanged. */
export function listFromArray(values: readonly number[]): ListNode | null {
    const dummy = new ListNode();
    let tail = dummy;
    for (const value of values) {
        tail.next = new ListNode(value);
        tail = tail.next;
    }
    return dummy.next;
}

/** O(n) time and O(n) output space; assumes an acyclic list. */
export function listToArray(head: ListNode | null): number[] {
    const values: number[] = [];
    let current = head;
    while (current !== null) {
        values.push(current.val);
        current = current.next;
    }
    return values;
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
