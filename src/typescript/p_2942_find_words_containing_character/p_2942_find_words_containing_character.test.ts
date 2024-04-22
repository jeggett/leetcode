import { findWordsContaining } from "./p_2942_find_words_containing_character.js";

test("problem 2942", () => {
  expect(findWordsContaining(["leet", "code"], "e")).toEqual([0, 1]);
  expect(findWordsContaining(["abc", "bcd", "aaaa", "cbc"], "a")).toEqual([
    0, 2,
  ]);
  expect(findWordsContaining(["abc", "bcd", "aaaa", "cbc"], "z")).toEqual([]);
});
