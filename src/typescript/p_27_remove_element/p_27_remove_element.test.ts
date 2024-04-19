import { removeElement } from "./p_27_remove_element";

test("problem p_27_remove_element", () => {
  const arr = [3, 2, 2, 3];
  expect(removeElement(arr, 3)).toEqual(2);
  expect(arr.slice(0, 2)).toEqual([2, 2]);
});
