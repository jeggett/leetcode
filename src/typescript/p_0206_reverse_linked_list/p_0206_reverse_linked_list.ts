/* time: O(n), space: O(1) */
export function reverseList(head: ListNode | null): ListNode | null {
    let prevPtr: ListNode | null = null;
    let currentPtr: ListNode | null = null;
    let nextPtr = head;

    while (nextPtr !== null) {
        currentPtr = nextPtr;
        nextPtr = nextPtr.next;
        currentPtr.next = prevPtr;
        prevPtr = currentPtr;
    }
    head = currentPtr;
    return head;
}
