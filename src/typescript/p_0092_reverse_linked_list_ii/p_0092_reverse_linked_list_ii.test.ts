import { LinkedList } from "../data_structures/linked_list.js";
import { reverseBetween } from "./p_0092_reverse_linked_list_ii.js";

const cases = [
    {
        name: "middle segment",
        values: [1, 2, 3, 4, 5],
        left: 2,
        right: 4,
        expected: [1, 4, 3, 2, 5],
    },
    { name: "whole list", values: [1, 2, 3], left: 1, right: 3, expected: [3, 2, 1] },
    { name: "single position", values: [1], left: 1, right: 1, expected: [1] },
];

test.each(cases)("$name", ({ values, left, right, expected }) => {
    const list = new LinkedList([...values]);
    const result = reverseBetween(list.head, left, right);
    const actual: number[] = [];
    let current = result;
    while (current !== null) {
        actual.push(current.val);
        current = current.next;
    }

    expect(actual).toEqual(expected);
});
