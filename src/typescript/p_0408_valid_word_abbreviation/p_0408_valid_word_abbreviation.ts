/* time: O(n), space: O(1) */

const isDigit = (str: string) => /^\d$/.test(str)
export function validWordAbbreviation(word: string, abbr: string): boolean {
  let wordIndex = 0;
  let abbrIndex = 0;
  while (wordIndex < word.length && abbrIndex < abbr.length) {
    if (word[wordIndex] !== abbr[abbrIndex]) {
      if (isDigit(abbr[abbrIndex])) {
        const digits = []
        while (isDigit(abbr[abbrIndex])) {
          digits.push(abbr[abbrIndex])
          abbrIndex++
        }
        if (digits[0] === '0') {
          return false;
        }
        const number= parseInt(digits.join(''), 10);
        for (let i = 0; i < number; i++) {
          wordIndex++;
        }
        if (wordIndex === word.length) {
          break;
        }
        continue;
      } else {
        return false;
      }
    }
    // case where the digit is at the end
    wordIndex++;
    abbrIndex++;
  }

  return wordIndex === word.length && abbrIndex === abbr.length;
};

// TODO compare with other people sulutions
