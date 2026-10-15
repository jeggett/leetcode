/* time: O(n), space: O(1) */
export function reverseBetween(
    head: ListNode | null,
    left: number,
    right: number,
): ListNode | null {
    if (head === null || left === right) return head;
    const sentinel: ListNode = { val: 0, next: head };
    let before = sentinel;
    for (let position = 1; position < left; position++) {
        if (before.next === null) return head;
        before = before.next;
    }
    const tail = before.next;
    if (tail === null) return head;
    // Move each following node to the front of the selected segment.
    for (let position = left; position < right && tail.next !== null; position++) {
        const node = tail.next;
        tail.next = node.next;
        node.next = before.next;
        before.next = node;
    }
    return sentinel.next;
}
