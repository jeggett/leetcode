import { LinkedList, LinkedListNode } from "../data_structures/linked_list.js";

type ListNode = LinkedListNode<number> | null;

/* time: O(n), space: O(1) */
export function reverseBetween(head: ListNode, left: number, right: number): ListNode {
    if (head === null || left === right) {
        return head;
    }
    // make indexes start from 0, not from 1
    const [leftIndex, rightIndex] = [left - 1, right - 1];

    let leftPtr: ListNode = head;
    let beforeLeftPtr: ListNode = null;
    let rightPtr: ListNode = null;
    let afterRightPtr: ListNode = null;

    if (leftIndex > 0) {
        beforeLeftPtr = head;
        let count = 0;
        while (count < leftIndex - 1 && beforeLeftPtr !== null) {
            beforeLeftPtr = beforeLeftPtr.next;
            count++;
        }
    }

    if (beforeLeftPtr !== null) {
        leftPtr = beforeLeftPtr.next;
    }

    if (rightIndex > leftIndex) {
        rightPtr = leftPtr;
        let count = 0;
        while (count < rightIndex - leftIndex && rightPtr !== null) {
            rightPtr = rightPtr.next;
            count++;
        }
    }

    if (rightPtr !== null && rightPtr.next !== null) {
        afterRightPtr = rightPtr.next;
    }

    let prev: ListNode = afterRightPtr;
    let current: ListNode = null;
    let follow: ListNode = leftPtr;
    while (follow !== afterRightPtr) {
        current = follow;
        if (follow !== null) follow = follow.next;
        if (current !== null) current.next = prev;
        prev = current;
    }

    // connect ends of the reversed segment properly
    if (beforeLeftPtr !== null) beforeLeftPtr.next = rightPtr;
    if (leftPtr !== null && afterRightPtr !== null) leftPtr.next = afterRightPtr;

    if (leftIndex === 0) {
        head = rightPtr;
    }

    return head;
}
