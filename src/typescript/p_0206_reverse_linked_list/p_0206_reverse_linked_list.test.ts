import { listFromArray, listToArray } from "../data_structures/helpers.js";
import { reverseList } from "./p_0206_reverse_linked_list.js";

test.each([
    { values: [], expected: [] },
    { values: [1], expected: [1] },
    { values: [1, 2, 3], expected: [3, 2, 1] },
    { values: [1, 1, 2], expected: [2, 1, 1] },
])("reverse $values", ({ values, expected }) => {
    expect(listToArray(reverseList(listFromArray(values)))).toEqual(expected);
});
