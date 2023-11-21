import {
  missingNumberHashMap,
  missingNumberSum,
} from "./p_0268_missing_number";

test("problem 0268", () => {
  expect(missingNumberHashMap([0, 1, 2, 3, 5])).toEqual(4);
  expect(missingNumberHashMap([0, 1])).toEqual(2);

  expect(missingNumberSum([0, 1, 2, 3, 5])).toEqual(4);
  expect(missingNumberSum([0, 1])).toEqual(2);
});
