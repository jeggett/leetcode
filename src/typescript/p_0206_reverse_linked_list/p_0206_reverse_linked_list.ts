import { LinkedListNode } from "../data_structures/linked_list";

type Node = LinkedListNode<number> | null

/* time: O(n), space: O(1) */
export function reverseList(head: Node): Node {
  let prevPtr: Node = null;
  let currentPtr: Node = null;
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
