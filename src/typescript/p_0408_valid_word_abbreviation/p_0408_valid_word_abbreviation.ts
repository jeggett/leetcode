/* time: O(n), space: O(1) */

const isDigit = (str: string) => /^\d$/.test(str);
export function validWordAbbreviation(word: string, abbr: string): boolean {
    let wordIndex = 0;
    let abbrIndex = 0;

    while (wordIndex < word.length && abbrIndex < abbr.length) {
        const abbreviationCharacter = abbr[abbrIndex];

        if (isDigit(abbreviationCharacter)) {
            if (abbreviationCharacter === "0") {
                return false;
            }

            let skippedCharacters = 0;
            while (abbrIndex < abbr.length && isDigit(abbr[abbrIndex])) {
                skippedCharacters = skippedCharacters * 10 + Number(abbr[abbrIndex]);
                if (skippedCharacters > word.length - wordIndex) {
                    return false;
                }
                abbrIndex++;
            }
            wordIndex += skippedCharacters;
            continue;
        }

        if (word[wordIndex] !== abbreviationCharacter) {
            return false;
        }

        wordIndex++;
        abbrIndex++;
    }

    return wordIndex === word.length && abbrIndex === abbr.length;
}
