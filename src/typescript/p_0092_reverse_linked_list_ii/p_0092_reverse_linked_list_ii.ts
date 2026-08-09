/* time: O(n), space: O(1) */
export function reverseBetween(
    head: ListNode | null,
    left: number,
    right: number,
): ListNode | null {
    if (head === null || left === right) {
        return head;
    }
    // make indexes start from 0, not from 1
    const [leftIndex, rightIndex] = [left - 1, right - 1];

    let leftPtr: ListNode | null = head;
    let beforeLeftPtr: ListNode | null = null;
    let rightPtr: ListNode | null = null;
    let afterRightPtr: ListNode | null = null;

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

    let prev: ListNode | null = afterRightPtr;
    let current: ListNode | null = null;
    let follow: ListNode | null = leftPtr;
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
