import { expect as leetExpect } from "./p_2704_to_be_or_not_to_be.js";

test("problem 2704", () => {
    expect(leetExpect(1).toBe(1)).toEqual(true);
    expect(() => leetExpect(1).toBe(2)).toThrow(new Error("Not Equal"));
    expect(leetExpect(1).notToBe(2)).toEqual(true);
    expect(() => leetExpect(1).notToBe(1)).toThrow(new Error("Equal"));
});
