import { validWordAbbreviation } from "./p_0408_valid_word_abbreviation.js";

test("problem 0408", () => {
    expect(validWordAbbreviation("substitution", "sub4u4")).toBe(true);
    expect(validWordAbbreviation("substitution", "s010n")).toBe(false);
    expect(validWordAbbreviation("a", "1")).toBe(true);
    expect(validWordAbbreviation("a", "2")).toBe(false);
    expect(validWordAbbreviation("word", "4")).toBe(true);
    expect(validWordAbbreviation("word", "5")).toBe(false);
    expect(validWordAbbreviation("word", "9999999999")).toBe(false);
    expect(validWordAbbreviation("word", "w02")).toBe(false);
});
