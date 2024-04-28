/* time O(n), space O(n) */
export function findDisappearedNumbers(nums: number[]): number[] {
    const result: number[] = [];
    // put numbers in range from 1 to nums.length to the correct position
    let i = 0;
    while (i < nums.length) {
        const j = nums[i] - 1;
        // i !== j is the swap condition, but we won't include it into
        // the if statement, because nums[i] !== nums[j] already implies i !== j.
        // nums[i] !== nums[j] prevents infinite loop of swaps of eqal numbers
        if (j < nums.length && nums[i] !== nums[j]) {
            [nums[i], nums[j]] = [nums[j], nums[i]];
        } else {
            // after the swap we don't want to iterate once
            i++;
        }
    }

    for (let i = 0; i < nums.length; i++) {
        // check for the the correct position
        if (nums[i] - 1 !== i) {
            result.push(i + 1);
        }
    }

    return result;
}
