import { validWordAbbreviation } from "./p_0408_valid_word_abbreviation";

test("problem 0408", () => {
  expect(validWordAbbreviation("substitution", "sub4u4")).toEqual(true);
  expect(validWordAbbreviation("substitution", "s010n")).toEqual(false);
});
