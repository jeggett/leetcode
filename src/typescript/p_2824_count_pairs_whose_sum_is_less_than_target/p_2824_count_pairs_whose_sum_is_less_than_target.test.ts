import { countPairs } from "./p_2824_count_pairs_whose_sum_is_less_than_target";

test("problem 2824", () => {
  expect(countPairs([-1, 1, 2, 3, 1], 2)).toEqual(3);
  expect(countPairs([-6, 2, 5, -2, -7, -1, 3], -2)).toEqual(10);
});
