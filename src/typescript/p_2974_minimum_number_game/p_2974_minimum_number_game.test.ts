import { numberGame } from "./p_2974_minimum_number_game.js";

test("problem 2974", () => {
    expect(numberGame([5, 4, 2, 3])).toEqual([3, 2, 5, 4]);
    expect(numberGame([2, 5])).toEqual([5, 2]);
    expect(numberGame([10, 2, 10, 1])).toEqual([2, 1, 10, 10]);
});
