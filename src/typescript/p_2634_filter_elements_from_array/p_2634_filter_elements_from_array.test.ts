import { filter } from "./p_2634_filter_elements_from_array.js";

test("problem 2634", () => {
  expect(filter([1, 3, 4, 2], (elem: number) => elem > 2)).toEqual([3, 4]);
});
