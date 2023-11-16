import { map } from "./p_2635_apply_transform_over_each_element_in_array";

test("problem 2635", () => {
  const arr = [1, 2, 3];
  expect(map(arr, (el) => el * 2)).toEqual([2, 4, 6]);
  expect(map(arr, () => 5)).toEqual([5, 5, 5]);
});
