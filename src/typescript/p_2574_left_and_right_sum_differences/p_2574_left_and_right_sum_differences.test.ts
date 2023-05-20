import { leftRightDifference } from "./p_2574_left_and_right_sum_differences";

test("problem 2574", () => {
  expect(leftRightDifference([10, 4, 8, 3])).toEqual([15, 1, 11, 22]);
  expect(leftRightDifference([1])).toEqual([0]);
});
