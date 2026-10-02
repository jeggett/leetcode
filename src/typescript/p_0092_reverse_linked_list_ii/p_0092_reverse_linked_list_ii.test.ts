import { listFromArray, listToArray } from "../data_structures/helpers.js";
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
    const result = reverseBetween(listFromArray(values), left, right);
    expect(listToArray(result)).toEqual(expected);
});
