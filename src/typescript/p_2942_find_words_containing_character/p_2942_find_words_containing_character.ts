/* time: O(n), space: O(1) */
export function findWordsContaining(words: string[], x: string): number[] {
  const result: number[] = [];
  for (const [index, word] of words.entries()) {
    if (word.includes(x)) {
      result.push(index);
    }
  }

  return result;
}
