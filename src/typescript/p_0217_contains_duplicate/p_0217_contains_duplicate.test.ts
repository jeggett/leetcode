import { containsDuplicate } from "./p_0217_contains_duplicate.js";

test("problem 0217", () => {
    expect(containsDuplicate([1, 2, 3, 2])).toEqual(true);
    expect(containsDuplicate([1, 2, 3, 4])).toEqual(false);
    expect(containsDuplicate([5])).toEqual(false);
    expect(containsDuplicate([])).toEqual(false);
});
