import { LinkedList } from "../data_structures/linked_list.js";
import { reverseBetween } from "./p_0092_reverse_linked_list_ii.js";

test("problem p_0092_reverse_linked_list_ii", () => {
    const ll = new LinkedList([1, 2, 3, 4, 5]);
    reverseBetween(ll.head, 2, 4);
    expect([...ll]).toEqual([1, 4, 3, 2, 5]);
});
