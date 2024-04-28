import { moveZeroes } from "./p_0283_move_zeroes.js";

test("problem 0283", () => {
    let nums = [0, 1, 0, 3, 12];
    moveZeroes(nums);
    expect(nums).toEqual([1, 3, 12, 0, 0]);

    nums = [0];
    moveZeroes(nums);
    expect(nums).toEqual([0]);

    nums = [1, 2, 3];
    moveZeroes(nums);
    expect(nums).toEqual([1, 2, 3]);
});
