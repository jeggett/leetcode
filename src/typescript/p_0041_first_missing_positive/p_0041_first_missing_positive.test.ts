import { firstMissingPositive } from "./p_0041_first_missing_positive";

test("problem 0041", () => {
  expect(firstMissingPositive([3, 4, -1, 1])).toEqual(2);
  expect(firstMissingPositive([1, 2, 0])).toEqual(3);
  expect(firstMissingPositive([7, 8, 9, 11, 12])).toEqual(1);
  expect(firstMissingPositive([1, 1])).toEqual(2);
  expect(firstMissingPositive([-1, -1])).toEqual(1);
  expect(firstMissingPositive([2, 1])).toEqual(3);
});
