import { LinkedList } from "./linked_list.js";

test("constructs a list without changing the input array", () => {
    const values = Object.freeze([1, 2, 3]);
    const list = new LinkedList(values);

    expect([...list]).toEqual([1, 2, 3]);
    expect(values).toEqual([1, 2, 3]);
    list.addFirst(0);
    expect([...list]).toEqual([0, 1, 2, 3]);
});

test("prepends to an empty list", () => {
    const list = new LinkedList<number>([]);
    expect([...list]).toEqual([]);
    list.addFirst(1);
    expect([...list]).toEqual([1]);
});
