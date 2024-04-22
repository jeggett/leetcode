import { reverseList } from "../p_0206_reverse_linked_list/p_0206_reverse_linked_list.js";

export class LinkedListNode<T> {
  val: T;
  next: LinkedListNode<T> | null;

  constructor(val: T) {
    this.val = val;
    this.next = null;
  }
}

export class LinkedList<T> {
  public head: LinkedListNode<T> | null;

  constructor(arr: T[]) {
    this.head = null;
    for (const elem of arr.reverse()) {
      this.addFirst(elem);
    }
  }

  *[Symbol.iterator]() {
    let current = this.head;
    while (current) {
      yield current.val;
      current = current.next;
    }
  }

  addFirst(val: T) {
    const node = new LinkedListNode(val);
    if (this.head === null) {
      this.head = node;
      return;
    }
    node.next = this.head;
    this.head = node;
  }
}
