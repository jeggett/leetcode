import { findDisappearedNumbers } from "./p_0448_find_all_numbers_disappeared_in_an_array.js";

test("problem 0448", () => {
    expect(findDisappearedNumbers([4, 3, 2, 7, 8, 2, 3, 1])).toEqual([5, 6]);
    expect(findDisappearedNumbers([1, 1])).toEqual([2]);
});
