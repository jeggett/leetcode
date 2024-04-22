import { findDuplicate } from "./p_0287_find_the_duplicate_number.js";

test("problem 0287", () => {
  expect(findDuplicate([1, 3, 4, 2, 2])).toEqual(2);
  expect(findDuplicate([3, 1, 3, 4, 2])).toEqual(3);
  expect(findDuplicate([4, 4, 4, 4, 4])).toEqual(4);
});
