import { LinkedList } from "../data_structures/linked_list.js";
import { reverseList } from "./p_0206_reverse_linked_list.js";

test("problem p_206_reverse_linked_list", () => {
  const list = new LinkedList([1, 2, 3]);
  list.head = reverseList(list.head);
  expect([...list]).toEqual([3, 2, 1]);

  const oneElemList = new LinkedList([1]);
  oneElemList.head = reverseList(oneElemList.head);
  expect([...oneElemList]).toEqual([1]);
});
