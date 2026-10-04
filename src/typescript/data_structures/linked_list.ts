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

    constructor(arr: readonly T[]) {
        this.head = null;
        for (let index = arr.length - 1; index >= 0; index--) {
            this.addFirst(arr[index]);
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
        node.next = this.head;
        this.head = node;
    }
}
