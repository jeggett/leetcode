import { circularArrayLoop } from "./p_457_circular_array_loop.js";

test("problem p_457_circular_array_loop", () => {
  expect(circularArrayLoop([2, -1, 1, 2, 2])).toEqual(true);
  expect(circularArrayLoop([-1, -2, -3, -4, -5, 6])).toEqual(false);
  expect(circularArrayLoop([1, -1, 5, 1, 4])).toEqual(true);
});
